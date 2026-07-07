//! Light semantic analysis: builds global symbol tables, resolves the entry
//! point, registers the `Option`/`Result` prelude, validates attributes, and
//! runs a mutability/assignability check. Deep static type inference is
//! intentionally light here — the interpreter carries runtime types and is the
//! reference semantics; this pass exists to catch the common compile-time errors
//! and to hand the back ends ready-made symbol tables.

use std::collections::HashMap;
use std::sync::Arc;

use myla_syntax::ast::*;
use myla_syntax::diagnostic::{Diagnostic, Stage};
use myla_syntax::span::Span;

mod check;

#[derive(Clone)]
pub struct TestCase {
    pub func: String,
    pub args: Vec<Expr>,
    pub expected: Expr,
    pub span: Span,
}

#[derive(Default)]
pub struct Analyzed {
    pub functions: HashMap<String, Arc<FunDecl>>,
    pub structs: HashMap<String, Arc<StructDecl>>,
    pub enums: HashMap<String, Arc<EnumDecl>>,
    pub actors: HashMap<String, Arc<ActorDecl>>,
    /// Unqualified variant name -> enum name (for `Some`/`None`/`Ok`/`Err` etc).
    pub variant_to_enum: HashMap<String, String>,
    /// (type name, method name) -> method.
    pub methods: HashMap<(String, String), Arc<FunDecl>>,
    pub consts: HashMap<String, Arc<ConstDecl>>,
    pub aliases: HashMap<String, TypeExpr>,
    pub entry: Option<String>,
    pub tests: Vec<TestCase>,
}

const BUILTIN_ATTRS: &[&str] = &["main", "test", "derive"];

/// Analyze a program, producing symbol tables or a list of diagnostics.
pub fn analyze(program: &Program) -> Result<Analyzed, Vec<Diagnostic>> {
    let mut a = Analyzed::default();
    let mut errors = Vec::new();

    register_prelude(&mut a);

    // First pass: collect declarations.
    for item in &program.items {
        match item {
            Item::Function(f) => {
                validate_attrs(f.name.as_str(), &f.attrs, &mut errors);
                collect_tests(&f.name, f, &mut a);
                if a.functions.contains_key(&f.name) {
                    errors.push(dup(&f.name, f.span));
                }
                a.functions.insert(f.name.clone(), Arc::new(f.clone()));
            }
            Item::Struct(s) => {
                if a.structs.contains_key(&s.name) {
                    errors.push(dup(&s.name, s.span));
                }
                a.structs.insert(s.name.clone(), Arc::new(s.clone()));
            }
            Item::Enum(e) => {
                for v in &e.variants {
                    a.variant_to_enum.insert(v.name.clone(), e.name.clone());
                }
                a.enums.insert(e.name.clone(), Arc::new(e.clone()));
            }
            Item::Actor(ac) => {
                for m in &ac.methods {
                    a.methods
                        .insert((ac.name.clone(), m.name.clone()), Arc::new(m.clone()));
                }
                a.actors.insert(ac.name.clone(), Arc::new(ac.clone()));
            }
            Item::Impl(im) => {
                let ty = impl_type_name(&im.type_name);
                for m in &im.methods {
                    a.methods
                        .insert((ty.clone(), m.name.clone()), Arc::new(m.clone()));
                }
            }
            Item::Trait(_) => {}
            Item::Const(c) => {
                a.consts.insert(c.name.clone(), Arc::new(c.clone()));
            }
            Item::TypeAlias(t) => {
                a.aliases.insert(t.name.clone(), t.target.clone());
            }
            Item::Import(_) => {}
        }
    }

    // Resolve entry point: explicit #main wins, else `main`.
    let mut main_attr = None;
    for item in &program.items {
        if let Item::Function(f) = item {
            if f.attrs.iter().any(|at| at.name == "main") {
                if main_attr.is_some() {
                    errors.push(Diagnostic::error(
                        Stage::Type,
                        "multiple `#main` entry points",
                        f.span,
                    ));
                }
                main_attr = Some(f.name.clone());
            }
        }
    }
    a.entry = main_attr.or_else(|| {
        if a.functions.contains_key("main") {
            Some("main".to_string())
        } else {
            None
        }
    });

    // Second pass: mutability / assignability checks over function bodies.
    check::check_program(program, &a, &mut errors);

    if errors.is_empty() {
        Ok(a)
    } else {
        Err(errors)
    }
}

fn register_prelude(a: &mut Analyzed) {
    a.variant_to_enum.insert("Some".into(), "Option".into());
    a.variant_to_enum.insert("None".into(), "Option".into());
    a.variant_to_enum.insert("Ok".into(), "Result".into());
    a.variant_to_enum.insert("Err".into(), "Result".into());
}

fn collect_tests(name: &str, f: &FunDecl, a: &mut Analyzed) {
    for at in &f.attrs {
        if at.name == "test" {
            if let Some(outputs) = &at.outputs {
                if let Some(expected) = outputs.first() {
                    a.tests.push(TestCase {
                        func: name.to_string(),
                        args: at.args.clone(),
                        expected: expected.clone(),
                        span: at.span,
                    });
                }
            }
        }
    }
}

fn validate_attrs(_owner: &str, attrs: &[Attribute], errors: &mut Vec<Diagnostic>) {
    for at in attrs {
        if !BUILTIN_ATTRS.contains(&at.name.as_str()) {
            errors.push(Diagnostic::error(
                Stage::Type,
                format!("unknown attribute `#{}`", at.name),
                at.span,
            ));
        }
    }
}

fn impl_type_name(ty: &TypeExpr) -> String {
    match &ty.kind {
        TypeKind::Named { name, .. } => name.clone(),
        TypeKind::List(_) => "list".into(),
        TypeKind::Map(..) => "map".into(),
        TypeKind::Tuple(_) => "tuple".into(),
        _ => "?".into(),
    }
}

fn dup(name: &str, span: Span) -> Diagnostic {
    Diagnostic::error(Stage::Type, format!("duplicate definition of `{name}`"), span)
}

/// Map a binary operator to the method name used for operator overloading.
pub fn operator_method(op: BinOp) -> Option<&'static str> {
    Some(match op {
        BinOp::Add => "add",
        BinOp::Sub => "sub",
        BinOp::Mul => "mul",
        BinOp::Div => "div",
        BinOp::Rem => "rem",
        BinOp::Eq | BinOp::Ne => "eq",
        BinOp::Lt | BinOp::Le | BinOp::Gt | BinOp::Ge => "cmp",
        _ => return None,
    })
}
