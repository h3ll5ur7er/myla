//! Native back end built on Cranelift.
//!
//! This lowers the **scalar / control-flow / function / print** core of Myla to
//! a native object file, which is then linked (with a tiny C runtime providing
//! `print`) into an executable via the system C compiler. The tree-walking
//! interpreter remains the full-feature reference; constructs the native back
//! end does not yet lower (closures, enums/match, collections, generics,
//! concurrency) produce a clear `unsupported` error so `myla build` degrades
//! gracefully while `myla run` handles the whole language.

use std::collections::HashMap;
use std::process::Command;

use cranelift_codegen::ir::{types, AbiParam, InstBuilder, Type, Value as CValue};
use cranelift_codegen::settings::{self, Configurable};
use cranelift_frontend::{FunctionBuilder, FunctionBuilderContext, Variable};
use cranelift_module::{DataDescription, DataId, FuncId, Linkage, Module};
use cranelift_object::{ObjectBuilder, ObjectModule};

use myla_sema::Analyzed;
use myla_syntax::ast::*;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Ty {
    Int,
    Float,
    Bool,
    Str,
    Unit,
}

impl Ty {
    fn clif(self) -> Type {
        match self {
            Ty::Float => types::F64,
            Ty::Unit => types::I64,
            _ => types::I64,
        }
    }
    fn from_name(name: &str) -> Ty {
        match name {
            "float" | "float32" | "float64" => Ty::Float,
            "bool" => Ty::Bool,
            "str" => Ty::Str,
            _ => Ty::Int,
        }
    }
}

pub fn build_executable(
    program: &Program,
    analyzed: &Analyzed,
    out_path: &str,
) -> Result<(), String> {
    let mut flags = settings::builder();
    flags.set("opt_level", "speed").ok();
    flags.set("is_pic", "true").ok();
    let isa_builder = cranelift_native::builder().map_err(|e| e.to_string())?;
    let isa = isa_builder
        .finish(settings::Flags::new(flags))
        .map_err(|e| e.to_string())?;
    let builder = ObjectBuilder::new(
        isa,
        "myla",
        cranelift_module::default_libcall_names(),
    )
    .map_err(|e| e.to_string())?;
    let mut module = ObjectModule::new(builder);

    let mut cg = Codegen::new(&mut module, analyzed);
    cg.declare_runtime()?;
    cg.declare_functions(program)?;
    cg.define_functions(program)?;
    cg.emit_c_main()?;

    let product = module.finish();
    let obj_bytes = product.emit().map_err(|e| e.to_string())?;

    let obj_path = format!("{out_path}.o");
    std::fs::write(&obj_path, obj_bytes).map_err(|e| e.to_string())?;

    // Compile the tiny C runtime and link everything into an executable.
    let rt_c = runtime_c_source();
    let rt_path = format!("{out_path}.rt.c");
    std::fs::write(&rt_path, rt_c).map_err(|e| e.to_string())?;

    let status = Command::new("cc")
        .args([&obj_path, &rt_path, "-o", out_path, "-lm"])
        .status()
        .map_err(|e| format!("failed to invoke cc: {e}"))?;
    let _ = std::fs::remove_file(&obj_path);
    let _ = std::fs::remove_file(&rt_path);
    if !status.success() {
        return Err("linking failed".into());
    }
    Ok(())
}

struct Codegen<'a> {
    module: &'a mut ObjectModule,
    a: &'a Analyzed,
    funcs: HashMap<String, (FuncId, Vec<Ty>, Ty)>,
    rt: HashMap<&'static str, FuncId>,
    strings: Vec<(DataId, String)>,
    str_counter: usize,
}

impl<'a> Codegen<'a> {
    fn new(module: &'a mut ObjectModule, a: &'a Analyzed) -> Self {
        Codegen {
            module,
            a,
            funcs: HashMap::new(),
            rt: HashMap::new(),
            strings: Vec::new(),
            str_counter: 0,
        }
    }

    fn declare_runtime(&mut self) -> Result<(), String> {
        let decls: &[(&str, &[Ty], Ty)] = &[
            ("myla_print_int", &[Ty::Int], Ty::Unit),
            ("myla_print_float", &[Ty::Float], Ty::Unit),
            ("myla_print_bool", &[Ty::Bool], Ty::Unit),
            ("myla_print_str", &[Ty::Str], Ty::Unit),
        ];
        for (name, params, ret) in decls {
            let mut sig = self.module.make_signature();
            for p in *params {
                sig.params.push(AbiParam::new(p.clif()));
            }
            if *ret != Ty::Unit {
                sig.returns.push(AbiParam::new(ret.clif()));
            }
            let id = self
                .module
                .declare_function(name, Linkage::Import, &sig)
                .map_err(|e| e.to_string())?;
            self.rt.insert(name, id);
        }
        Ok(())
    }

    fn declare_functions(&mut self, program: &Program) -> Result<(), String> {
        for item in &program.items {
            if let Item::Function(f) = item {
                if !f.generics.is_empty() || f.is_async {
                    continue;
                }
                let param_tys: Vec<Ty> = f
                    .params
                    .iter()
                    .map(|p| p.ty.as_ref().map(|t| type_name_of(t)).map(|n| Ty::from_name(&n)).unwrap_or(Ty::Int))
                    .collect();
                let ret_ty = f
                    .ret
                    .as_ref()
                    .map(|t| Ty::from_name(&type_name_of(t)))
                    .unwrap_or(Ty::Unit);
                let mut sig = self.module.make_signature();
                for p in &param_tys {
                    sig.params.push(AbiParam::new(p.clif()));
                }
                if ret_ty != Ty::Unit {
                    sig.returns.push(AbiParam::new(ret_ty.clif()));
                }
                let linkage = Linkage::Local;
                let id = self
                    .module
                    .declare_function(&mangle(&f.name), linkage, &sig)
                    .map_err(|e| e.to_string())?;
                self.funcs.insert(f.name.clone(), (id, param_tys, ret_ty));
            }
        }
        Ok(())
    }

    fn define_functions(&mut self, program: &Program) -> Result<(), String> {
        for item in &program.items {
            if let Item::Function(f) = item {
                if !self.funcs.contains_key(&f.name) {
                    continue;
                }
                self.define_one(f)?;
            }
        }
        Ok(())
    }

    fn define_one(&mut self, f: &FunDecl) -> Result<(), String> {
        let (id, param_tys, ret_ty) = self.funcs.get(&f.name).cloned().unwrap();
        let mut ctx = self.module.make_context();
        let mut sig = self.module.make_signature();
        for p in &param_tys {
            sig.params.push(AbiParam::new(p.clif()));
        }
        if ret_ty != Ty::Unit {
            sig.returns.push(AbiParam::new(ret_ty.clif()));
        }
        ctx.func.signature = sig;

        let mut fbctx = FunctionBuilderContext::new();
        let mut fctx = FnCtx {
            vars: HashMap::new(),
            var_tys: HashMap::new(),
            next_var: 0,
        };

        {
            let mut builder = FunctionBuilder::new(&mut ctx.func, &mut fbctx);
            let entry = builder.create_block();
            builder.append_block_params_for_function_params(entry);
            builder.switch_to_block(entry);
            builder.seal_block(entry);

            for (i, p) in f.params.iter().enumerate() {
                let val = builder.block_params(entry)[i];
                let var = Variable::from_u32(fctx.next_var as u32);
                fctx.next_var += 1;
                builder.declare_var(var, param_tys[i].clif());
                builder.def_var(var, val);
                fctx.vars.insert(p.name.clone(), var);
                fctx.var_tys.insert(p.name.clone(), param_tys[i]);
            }

            let mut lowerer = Lowerer {
                builder,
                module: self.module,
                funcs: &self.funcs,
                rt: &self.rt,
                strings: &mut self.strings,
                str_counter: &mut self.str_counter,
                fctx: &mut fctx,
            };
            lowerer.lower_block(&f.body)?;
            // implicit return for void functions
            if ret_ty == Ty::Unit {
                lowerer.builder.ins().return_(&[]);
            } else {
                // fall-through safety: return zero
                let zero = lowerer.zero(ret_ty);
                lowerer.builder.ins().return_(&[zero]);
            }
            lowerer.builder.finalize();
        }

        self.module
            .define_function(id, &mut ctx)
            .map_err(|e| format!("{}: {e}", f.name))?;
        self.module.clear_context(&mut ctx);
        Ok(())
    }

    fn emit_c_main(&mut self) -> Result<(), String> {
        let entry = match &self.a.entry {
            Some(e) => e.clone(),
            None => return Err("no entry point".into()),
        };
        let (entry_id, _, _) = self
            .funcs
            .get(&entry)
            .cloned()
            .ok_or("entry point not compiled (uses unsupported features)")?;

        let mut sig = self.module.make_signature();
        sig.returns.push(AbiParam::new(types::I32));
        let main_id = self
            .module
            .declare_function("main", Linkage::Export, &sig)
            .map_err(|e| e.to_string())?;
        let mut ctx = self.module.make_context();
        ctx.func.signature = sig;
        let mut fbctx = FunctionBuilderContext::new();
        {
            let mut builder = FunctionBuilder::new(&mut ctx.func, &mut fbctx);
            let block = builder.create_block();
            builder.switch_to_block(block);
            builder.seal_block(block);
            let callee = self.module.declare_func_in_func(entry_id, builder.func);
            builder.ins().call(callee, &[]);
            let zero = builder.ins().iconst(types::I32, 0);
            builder.ins().return_(&[zero]);
            builder.finalize();
        }
        self.module
            .define_function(main_id, &mut ctx)
            .map_err(|e| e.to_string())?;
        self.module.clear_context(&mut ctx);
        Ok(())
    }
}

struct FnCtx {
    vars: HashMap<String, Variable>,
    var_tys: HashMap<String, Ty>,
    next_var: usize,
}

struct Lowerer<'a, 'b> {
    builder: FunctionBuilder<'b>,
    module: &'a mut ObjectModule,
    funcs: &'a HashMap<String, (FuncId, Vec<Ty>, Ty)>,
    rt: &'a HashMap<&'static str, FuncId>,
    strings: &'a mut Vec<(DataId, String)>,
    str_counter: &'a mut usize,
    fctx: &'a mut FnCtx,
}

impl Lowerer<'_, '_> {
    fn zero(&mut self, ty: Ty) -> CValue {
        match ty {
            Ty::Float => self.builder.ins().f64const(0.0),
            _ => self.builder.ins().iconst(types::I64, 0),
        }
    }

    fn lower_block(&mut self, block: &Block) -> Result<(), String> {
        for stmt in &block.stmts {
            self.lower_stmt(stmt)?;
        }
        if let Some(tail) = &block.tail {
            self.lower_expr(tail)?;
        }
        Ok(())
    }

    fn lower_stmt(&mut self, stmt: &Stmt) -> Result<(), String> {
        match &stmt.kind {
            StmtKind::Let { name, init, .. } => {
                let (val, ty) = self.lower_expr(init)?;
                let var = Variable::from_u32(self.fctx.next_var as u32);
                self.fctx.next_var += 1;
                self.builder.declare_var(var, ty.clif());
                self.builder.def_var(var, val);
                self.fctx.vars.insert(name.clone(), var);
                self.fctx.var_tys.insert(name.clone(), ty);
                Ok(())
            }
            StmtKind::Assign { target, op, value } => {
                let name = match &target.kind {
                    ExprKind::Name(n) => n.clone(),
                    _ => return Err("native backend only supports simple variable assignment".into()),
                };
                let var = *self
                    .fctx
                    .vars
                    .get(&name)
                    .ok_or_else(|| format!("unknown variable `{name}`"))?;
                let ty = self.fctx.var_tys[&name];
                let (mut val, _) = self.lower_expr(value)?;
                if let Some(binop) = op {
                    let cur = self.builder.use_var(var);
                    val = self.lower_binop(*binop, cur, val, ty)?.0;
                }
                self.builder.def_var(var, val);
                Ok(())
            }
            StmtKind::Expr(e) => {
                self.lower_expr(e)?;
                Ok(())
            }
            StmtKind::Return(value) => {
                match value {
                    Some(e) => {
                        let (val, _) = self.lower_expr(e)?;
                        self.builder.ins().return_(&[val]);
                    }
                    None => {
                        self.builder.ins().return_(&[]);
                    }
                }
                // start an unreachable block so following code is valid
                let cont = self.builder.create_block();
                self.builder.switch_to_block(cont);
                self.builder.seal_block(cont);
                Ok(())
            }
            StmtKind::While { cond, body } => {
                let header = self.builder.create_block();
                let body_block = self.builder.create_block();
                let exit = self.builder.create_block();
                self.builder.ins().jump(header, &[]);
                self.builder.switch_to_block(header);
                let (c, _) = self.lower_expr(cond)?;
                self.builder.ins().brif(c, body_block, &[], exit, &[]);
                self.builder.switch_to_block(body_block);
                self.builder.seal_block(body_block);
                self.lower_block(body)?;
                self.builder.ins().jump(header, &[]);
                self.builder.seal_block(header);
                self.builder.switch_to_block(exit);
                self.builder.seal_block(exit);
                Ok(())
            }
            StmtKind::For { var, iter, body } => {
                let (start, end) = match &iter.kind {
                    ExprKind::Range { start, end } => (start, end),
                    _ => return Err("native backend only supports `for x in a..b` ranges".into()),
                };
                let (s, _) = self.lower_expr(start)?;
                let (e, _) = self.lower_expr(end)?;
                let loopvar = Variable::from_u32(self.fctx.next_var as u32);
                self.fctx.next_var += 1;
                self.builder.declare_var(loopvar, types::I64);
                self.builder.def_var(loopvar, s);
                self.fctx.vars.insert(var.clone(), loopvar);
                self.fctx.var_tys.insert(var.clone(), Ty::Int);

                let endvar = Variable::from_u32(self.fctx.next_var as u32);
                self.fctx.next_var += 1;
                self.builder.declare_var(endvar, types::I64);
                self.builder.def_var(endvar, e);

                let header = self.builder.create_block();
                let body_block = self.builder.create_block();
                let exit = self.builder.create_block();
                self.builder.ins().jump(header, &[]);
                self.builder.switch_to_block(header);
                let cur = self.builder.use_var(loopvar);
                let endv = self.builder.use_var(endvar);
                let cmp = self.builder.ins().icmp(
                    cranelift_codegen::ir::condcodes::IntCC::SignedLessThan,
                    cur,
                    endv,
                );
                self.builder.ins().brif(cmp, body_block, &[], exit, &[]);
                self.builder.switch_to_block(body_block);
                self.builder.seal_block(body_block);
                self.lower_block(body)?;
                let cur2 = self.builder.use_var(loopvar);
                let one = self.builder.ins().iconst(types::I64, 1);
                let next = self.builder.ins().iadd(cur2, one);
                self.builder.def_var(loopvar, next);
                self.builder.ins().jump(header, &[]);
                self.builder.seal_block(header);
                self.builder.switch_to_block(exit);
                self.builder.seal_block(exit);
                Ok(())
            }
            StmtKind::Break | StmtKind::Continue => {
                Err("native backend does not yet support break/continue".into())
            }
            StmtKind::Select(_) => Err("native backend does not support `select`".into()),
        }
    }

    fn lower_expr(&mut self, expr: &Expr) -> Result<(CValue, Ty), String> {
        match &expr.kind {
            ExprKind::Int { text } => {
                let (v, _) = myla_int_literal(text);
                Ok((self.builder.ins().iconst(types::I64, v as i64), Ty::Int))
            }
            ExprKind::Float { text } => {
                let v = myla_float_literal(text);
                Ok((self.builder.ins().f64const(v), Ty::Float))
            }
            ExprKind::Bool(b) => {
                Ok((self.builder.ins().iconst(types::I64, *b as i64), Ty::Bool))
            }
            ExprKind::Str(s) => {
                let val = self.string_ptr(s);
                Ok((val, Ty::Str))
            }
            ExprKind::Name(n) => {
                let var = *self
                    .fctx
                    .vars
                    .get(n)
                    .ok_or_else(|| format!("native backend: unknown name `{n}`"))?;
                let ty = self.fctx.var_tys[n];
                Ok((self.builder.use_var(var), ty))
            }
            ExprKind::Unary { op, expr: inner } => {
                let (v, ty) = self.lower_expr(inner)?;
                match op {
                    UnOp::Neg if ty == Ty::Float => Ok((self.builder.ins().fneg(v), Ty::Float)),
                    UnOp::Neg => Ok((self.builder.ins().ineg(v), Ty::Int)),
                    UnOp::Not => {
                        let one = self.builder.ins().iconst(types::I64, 1);
                        Ok((self.builder.ins().bxor(v, one), Ty::Bool))
                    }
                    UnOp::BitNot => Ok((self.builder.ins().bnot(v), Ty::Int)),
                }
            }
            ExprKind::Binary { op, lhs, rhs } => {
                let (l, lt) = self.lower_expr(lhs)?;
                let (r, _) = self.lower_expr(rhs)?;
                self.lower_binop(*op, l, r, lt)
            }
            ExprKind::Call { callee, args } => self.lower_call(callee, args),
            ExprKind::Cast { expr: inner, ty } => {
                let (v, vt) = self.lower_expr(inner)?;
                let target = Ty::from_name(&type_name_of(ty));
                Ok((self.convert(v, vt, target), target))
            }
            ExprKind::Block(b) => {
                self.lower_block(b)?;
                Ok((self.builder.ins().iconst(types::I64, 0), Ty::Unit))
            }
            ExprKind::If { cond, then, otherwise } => {
                let (c, _) = self.lower_expr(cond)?;
                let then_b = self.builder.create_block();
                let else_b = self.builder.create_block();
                let merge = self.builder.create_block();
                self.builder.ins().brif(c, then_b, &[], else_b, &[]);

                self.builder.switch_to_block(then_b);
                self.builder.seal_block(then_b);
                self.lower_block(then)?;
                self.builder.ins().jump(merge, &[]);

                self.builder.switch_to_block(else_b);
                self.builder.seal_block(else_b);
                if let Some(e) = otherwise {
                    self.lower_expr(e)?;
                }
                self.builder.ins().jump(merge, &[]);

                self.builder.switch_to_block(merge);
                self.builder.seal_block(merge);
                Ok((self.builder.ins().iconst(types::I64, 0), Ty::Unit))
            }
            _ => Err("native backend does not yet support this expression".into()),
        }
    }

    fn convert(&mut self, v: CValue, from: Ty, to: Ty) -> CValue {
        match (from, to) {
            (Ty::Int, Ty::Float) | (Ty::Bool, Ty::Float) => self.builder.ins().fcvt_from_sint(types::F64, v),
            (Ty::Float, Ty::Int) => self.builder.ins().fcvt_to_sint(types::I64, v),
            _ => v,
        }
    }

    fn lower_binop(&mut self, op: BinOp, l: CValue, r: CValue, lt: Ty) -> Result<(CValue, Ty), String> {
        use cranelift_codegen::ir::condcodes::{FloatCC, IntCC};
        use BinOp::*;
        if lt == Ty::Float {
            let v = match op {
                Add => self.builder.ins().fadd(l, r),
                Sub => self.builder.ins().fsub(l, r),
                Mul => self.builder.ins().fmul(l, r),
                Div => self.builder.ins().fdiv(l, r),
                Lt => return Ok((self.fcmp(FloatCC::LessThan, l, r), Ty::Bool)),
                Le => return Ok((self.fcmp(FloatCC::LessThanOrEqual, l, r), Ty::Bool)),
                Gt => return Ok((self.fcmp(FloatCC::GreaterThan, l, r), Ty::Bool)),
                Ge => return Ok((self.fcmp(FloatCC::GreaterThanOrEqual, l, r), Ty::Bool)),
                Eq => return Ok((self.fcmp(FloatCC::Equal, l, r), Ty::Bool)),
                Ne => return Ok((self.fcmp(FloatCC::NotEqual, l, r), Ty::Bool)),
                _ => return Err("invalid float operator in native backend".into()),
            };
            return Ok((v, Ty::Float));
        }
        let v = match op {
            Add => self.builder.ins().iadd(l, r),
            Sub => self.builder.ins().isub(l, r),
            Mul => self.builder.ins().imul(l, r),
            Div => self.builder.ins().sdiv(l, r),
            Rem => self.builder.ins().srem(l, r),
            BitAnd => self.builder.ins().band(l, r),
            BitOr => self.builder.ins().bor(l, r),
            BitXor => self.builder.ins().bxor(l, r),
            Shl => self.builder.ins().ishl(l, r),
            Shr => self.builder.ins().sshr(l, r),
            And => self.builder.ins().band(l, r),
            Or => self.builder.ins().bor(l, r),
            Lt => return Ok((self.icmp(IntCC::SignedLessThan, l, r), Ty::Bool)),
            Le => return Ok((self.icmp(IntCC::SignedLessThanOrEqual, l, r), Ty::Bool)),
            Gt => return Ok((self.icmp(IntCC::SignedGreaterThan, l, r), Ty::Bool)),
            Ge => return Ok((self.icmp(IntCC::SignedGreaterThanOrEqual, l, r), Ty::Bool)),
            Eq => return Ok((self.icmp(IntCC::Equal, l, r), Ty::Bool)),
            Ne => return Ok((self.icmp(IntCC::NotEqual, l, r), Ty::Bool)),
        };
        Ok((v, Ty::Int))
    }

    fn icmp(&mut self, cc: cranelift_codegen::ir::condcodes::IntCC, l: CValue, r: CValue) -> CValue {
        let b = self.builder.ins().icmp(cc, l, r);
        self.builder.ins().uextend(types::I64, b)
    }
    fn fcmp(&mut self, cc: cranelift_codegen::ir::condcodes::FloatCC, l: CValue, r: CValue) -> CValue {
        let b = self.builder.ins().fcmp(cc, l, r);
        self.builder.ins().uextend(types::I64, b)
    }

    fn lower_call(&mut self, callee: &Expr, args: &[Expr]) -> Result<(CValue, Ty), String> {
        let name = match &callee.kind {
            ExprKind::Name(n) => n.clone(),
            _ => return Err("native backend only supports direct function calls".into()),
        };
        if name == "print" {
            let (v, ty) = self.lower_expr(&args[0])?;
            let rt_name = match ty {
                Ty::Float => "myla_print_float",
                Ty::Bool => "myla_print_bool",
                Ty::Str => "myla_print_str",
                _ => "myla_print_int",
            };
            let id = self.rt[rt_name];
            let callee_ref = self.module.declare_func_in_func(id, self.builder.func);
            self.builder.ins().call(callee_ref, &[v]);
            let zero = self.builder.ins().iconst(types::I64, 0);
            return Ok((zero, Ty::Unit));
        }
        let (id, param_tys, ret_ty) = self
            .funcs
            .get(&name)
            .cloned()
            .ok_or_else(|| format!("native backend: unknown function `{name}`"))?;
        let mut vals = Vec::new();
        for (i, a) in args.iter().enumerate() {
            let (v, vt) = self.lower_expr(a)?;
            let want = param_tys.get(i).copied().unwrap_or(vt);
            vals.push(self.convert(v, vt, want));
        }
        let callee_ref = self.module.declare_func_in_func(id, self.builder.func);
        let call = self.builder.ins().call(callee_ref, &vals);
        if ret_ty == Ty::Unit {
            let zero = self.builder.ins().iconst(types::I64, 0);
            Ok((zero, Ty::Unit))
        } else {
            let res = self.builder.inst_results(call)[0];
            Ok((res, ret_ty))
        }
    }

    fn string_ptr(&mut self, s: &str) -> CValue {
        let name = format!("str{}", *self.str_counter);
        *self.str_counter += 1;
        let mut bytes = s.as_bytes().to_vec();
        bytes.push(0);
        let data_id = self
            .module
            .declare_data(&name, Linkage::Local, false, false)
            .unwrap();
        let mut desc = DataDescription::new();
        desc.define(bytes.into_boxed_slice());
        self.module.define_data(data_id, &desc).unwrap();
        self.strings.push((data_id, s.to_string()));
        let gv = self.module.declare_data_in_func(data_id, self.builder.func);
        self.builder.ins().symbol_value(types::I64, gv)
    }
}

fn mangle(name: &str) -> String {
    format!("myla_user_{name}")
}

fn type_name_of(ty: &TypeExpr) -> String {
    match &ty.kind {
        TypeKind::Named { name, .. } => name.clone(),
        _ => "?".into(),
    }
}

fn myla_int_literal(text: &str) -> (i128, ()) {
    let clean: String = text
        .trim_end_matches(|c: char| c.is_ascii_alphabetic())
        .chars()
        .filter(|c| *c != '_')
        .collect();
    let v = if let Some(h) = clean.strip_prefix("0x") {
        i128::from_str_radix(h, 16).unwrap_or(0)
    } else if let Some(b) = clean.strip_prefix("0b") {
        i128::from_str_radix(b, 2).unwrap_or(0)
    } else if let Some(o) = clean.strip_prefix("0o") {
        i128::from_str_radix(o, 8).unwrap_or(0)
    } else {
        clean.parse().unwrap_or(0)
    };
    (v, ())
}

fn myla_float_literal(text: &str) -> f64 {
    let body = text.trim_end_matches("f32").trim_end_matches("f64");
    let clean: String = body.chars().filter(|c| *c != '_').collect();
    clean.parse().unwrap_or(0.0)
}

fn runtime_c_source() -> &'static str {
    r#"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
void myla_print_int(long long v) { printf("%lld\n", v); }
void myla_print_bool(long long v) { printf(v ? "true\n" : "false\n"); }
void myla_print_str(const char* s) { printf("%s\n", s); }
void myla_print_float(double v) {
    char buf[64];
    int prec;
    for (prec = 1; prec <= 17; prec++) {
        snprintf(buf, sizeof buf, "%.*g", prec, v);
        if (strtod(buf, NULL) == v) break;
    }
    /* ensure a decimal point so floats are distinguishable from ints */
    if (!strpbrk(buf, ".eEnN")) {
        size_t n = strlen(buf);
        buf[n] = '.'; buf[n+1] = '0'; buf[n+2] = '\0';
    }
    printf("%s\n", buf);
}
"#
}
