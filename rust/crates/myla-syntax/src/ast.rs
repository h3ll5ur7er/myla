//! Abstract syntax tree.

use crate::span::Span;

#[derive(Clone, Debug)]
pub struct Program {
    pub items: Vec<Item>,
}

#[derive(Clone, Debug)]
pub struct Attribute {
    pub name: String,
    pub args: Vec<Expr>,
    pub outputs: Option<Vec<Expr>>,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum Item {
    Function(FunDecl),
    Struct(StructDecl),
    Enum(EnumDecl),
    Trait(TraitDecl),
    Impl(ImplDecl),
    TypeAlias(TypeAliasDecl),
    Const(ConstDecl),
    Import(ImportDecl),
    Actor(ActorDecl),
}

#[derive(Clone, Debug)]
pub struct GenericParam {
    pub name: String,
    pub bounds: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct FunDecl {
    pub name: String,
    pub generics: Vec<GenericParam>,
    pub params: Vec<Param>,
    pub ret: Option<TypeExpr>,
    pub body: Block,
    pub is_async: bool,
    pub attrs: Vec<Attribute>,
    pub is_pub: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Param {
    pub name: String,
    pub ty: Option<TypeExpr>,
    /// `self` / `var self` receiver.
    pub is_self: bool,
    pub self_mut: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct StructDecl {
    pub name: String,
    pub generics: Vec<GenericParam>,
    pub fields: Vec<Field>,
    pub attrs: Vec<Attribute>,
    pub is_pub: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Field {
    pub name: String,
    pub ty: TypeExpr,
}

#[derive(Clone, Debug)]
pub struct EnumDecl {
    pub name: String,
    pub generics: Vec<GenericParam>,
    pub variants: Vec<Variant>,
    pub attrs: Vec<Attribute>,
    pub is_pub: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Variant {
    pub name: String,
    pub payload: Vec<TypeExpr>,
}

#[derive(Clone, Debug)]
pub struct TraitDecl {
    pub name: String,
    pub generics: Vec<GenericParam>,
    pub methods: Vec<FunDecl>,
    pub is_pub: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct ImplDecl {
    pub generics: Vec<GenericParam>,
    /// `impl Trait for Type` -> `Some("Trait")`; inherent impl -> `None`.
    pub trait_name: Option<String>,
    pub type_name: TypeExpr,
    pub methods: Vec<FunDecl>,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct TypeAliasDecl {
    pub name: String,
    pub target: TypeExpr,
    pub is_pub: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct ConstDecl {
    pub name: String,
    pub ty: TypeExpr,
    pub value: Expr,
    pub is_pub: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct ImportDecl {
    /// `import a.b.c` -> path = ["a","b","c"], items = None.
    /// `from a.b import x, y` -> path = ["a","b"], items = Some([(x,None),...]).
    pub path: Vec<String>,
    pub items: Option<Vec<(String, Option<String>)>>,
    pub alias: Option<String>,
    pub is_pub: bool,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct ActorDecl {
    pub name: String,
    pub fields: Vec<Field>,
    pub methods: Vec<FunDecl>,
    pub is_pub: bool,
    pub span: Span,
}

// --- Types ---

#[derive(Clone, Debug)]
pub struct TypeExpr {
    pub kind: TypeKind,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum TypeKind {
    /// Named type, possibly generic: `int`, `Point`, `Option<int>`.
    Named { name: String, args: Vec<TypeExpr> },
    Tuple(Vec<TypeExpr>),
    List(Box<TypeExpr>),
    Map(Box<TypeExpr>, Box<TypeExpr>),
    Chan(Box<TypeExpr>),
    Func { params: Vec<TypeExpr>, ret: Box<TypeExpr> },
    SelfType,
}

// --- Statements & blocks ---

#[derive(Clone, Debug)]
pub struct Block {
    pub stmts: Vec<Stmt>,
    /// Optional trailing expression that gives the block its value.
    pub tail: Option<Box<Expr>>,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Stmt {
    pub kind: StmtKind,
    pub span: Span,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LetKind {
    Let,
    Var,
}

#[derive(Clone, Debug)]
pub enum StmtKind {
    Let {
        kind: LetKind,
        name: String,
        ty: Option<TypeExpr>,
        init: Expr,
    },
    Assign {
        target: Expr,
        op: Option<BinOp>,
        value: Expr,
    },
    Expr(Expr),
    Return(Option<Expr>),
    While {
        cond: Expr,
        body: Block,
    },
    For {
        var: String,
        iter: Expr,
        body: Block,
    },
    Break,
    Continue,
    /// `select { recv x from ch => ..., ... }` (bonus concurrency).
    Select(Vec<SelectArm>),
}

#[derive(Clone, Debug)]
pub struct SelectArm {
    pub binding: Option<String>,
    pub channel: Expr,
    pub body: Block,
}

// --- Expressions ---

#[derive(Clone, Debug)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BinOp {
    Add, Sub, Mul, Div, Rem,
    Eq, Ne, Lt, Le, Gt, Ge,
    And, Or,
    BitAnd, BitOr, BitXor, Shl, Shr,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UnOp {
    Neg,
    Not,
    BitNot,
}

#[derive(Clone, Debug)]
pub enum ExprKind {
    Int { text: String },
    Float { text: String },
    Str(String),
    FStr(Vec<FStrPart>),
    Char(char),
    Bool(bool),
    Name(String),
    /// `_` placeholder for partial application.
    Hole,
    SelfExpr,
    Unary { op: UnOp, expr: Box<Expr> },
    Binary { op: BinOp, lhs: Box<Expr>, rhs: Box<Expr> },
    Call { callee: Box<Expr>, args: Vec<Expr> },
    MethodCall { recv: Box<Expr>, method: String, args: Vec<Expr> },
    Field { recv: Box<Expr>, name: String },
    Index { recv: Box<Expr>, index: Box<Expr> },
    StructLit { name: String, fields: Vec<(String, Expr)> },
    ListLit(Vec<Expr>),
    MapLit(Vec<(Expr, Expr)>),
    TupleLit(Vec<Expr>),
    Lambda { params: Vec<Param>, body: Box<Expr> },
    If { cond: Box<Expr>, then: Block, otherwise: Option<Box<Expr>> },
    Match { scrutinee: Box<Expr>, arms: Vec<MatchArm> },
    Block(Block),
    Range { start: Box<Expr>, end: Box<Expr> },
    Cast { expr: Box<Expr>, ty: TypeExpr },
    Pipe { lhs: Box<Expr>, rhs: Box<Expr> },
    Try(Box<Expr>),
    Await(Box<Expr>),
    Spawn(Box<Expr>),
}

#[derive(Clone, Debug)]
pub enum FStrPart {
    Lit(String),
    Expr(Box<Expr>),
}

#[derive(Clone, Debug)]
pub struct MatchArm {
    pub pattern: Pattern,
    pub guard: Option<Expr>,
    pub body: Expr,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Pattern {
    pub kind: PatternKind,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum PatternKind {
    Wildcard,
    Binding(String),
    Int(String),
    Bool(bool),
    Str(String),
    Char(char),
    Tuple(Vec<Pattern>),
    /// `Enum.Variant(sub...)` or `.Variant` or `Variant`.
    Variant { path: Vec<String>, sub: Vec<Pattern> },
    Struct { name: String, fields: Vec<(String, Pattern)> },
    Or(Vec<Pattern>),
}
