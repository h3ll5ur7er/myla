//! The runtime value model for the interpreter.
//!
//! Values are `Clone + Send + Sync` so they can cross task/channel boundaries.
//! Aggregates share via `Arc` and mutate copy-on-write (`Arc::make_mut`), which
//! gives value semantics without O(n) copies when simply threading data around.

use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::sync::{Arc, Mutex};

use myla_runtime::concurrency::{Channel, Task};
use myla_runtime::{format_float, IntKind};
use myla_syntax::ast::{ActorDecl, Expr, FunDecl, Param};

#[derive(Clone)]
pub enum Value {
    Unit,
    Int(i128, IntKind),
    Float(f64, u8),
    Bool(bool),
    Char(char),
    Str(Arc<str>),
    Tuple(Arc<Vec<Value>>),
    List(Arc<Vec<Value>>),
    Map(Arc<OrderedMap>),
    Struct(Arc<StructVal>),
    Enum(Arc<EnumVal>),
    Closure(Arc<Closure>),
    Func(Arc<FunDecl>),
    Partial(Arc<Partial>),
    Builtin(&'static str),
    Chan(Channel<Value>),
    Task(Arc<Task<Value>>),
    Actor(Arc<ActorHandle>),
}

#[derive(Clone)]
pub struct StructVal {
    pub name: String,
    pub fields: Vec<(String, Value)>,
}

impl StructVal {
    pub fn get(&self, name: &str) -> Option<&Value> {
        self.fields.iter().find(|(n, _)| n == name).map(|(_, v)| v)
    }
    pub fn get_mut(&mut self, name: &str) -> Option<&mut Value> {
        self.fields.iter_mut().find(|(n, _)| n == name).map(|(_, v)| v)
    }
}

#[derive(Clone)]
pub struct EnumVal {
    pub enum_name: String,
    pub variant: String,
    pub payload: Vec<Value>,
}

#[derive(Clone)]
pub struct Closure {
    pub params: Vec<Param>,
    pub body: Arc<Expr>,
    pub captured: HashMap<String, Value>,
    pub is_async: bool,
}

/// A partially-applied callable: `slots` holds filled args with `None` for holes.
#[derive(Clone)]
pub struct Partial {
    pub callee: Value,
    pub slots: Vec<Option<Value>>,
}

pub struct ActorHandle {
    pub name: String,
    pub decl: Arc<ActorDecl>,
    pub state: Mutex<HashMap<String, Value>>,
}

/// An insertion-ordered map with arbitrary value keys (fixes the original's
/// scalar-only key limitation). Lookups are O(1) via a hash index.
#[derive(Clone, Default)]
pub struct OrderedMap {
    pub entries: Vec<(Value, Value)>,
    index: HashMap<u64, Vec<usize>>,
}

impl OrderedMap {
    pub fn new() -> Self {
        OrderedMap::default()
    }

    fn hash_key(k: &Value) -> u64 {
        let mut h = std::collections::hash_map::DefaultHasher::new();
        k.hash(&mut h);
        h.finish()
    }

    pub fn get(&self, key: &Value) -> Option<&Value> {
        let h = Self::hash_key(key);
        for &i in self.index.get(&h)?.iter() {
            if value_eq(&self.entries[i].0, key) {
                return Some(&self.entries[i].1);
            }
        }
        None
    }

    pub fn get_mut(&mut self, key: &Value) -> Option<&mut Value> {
        let h = Self::hash_key(key);
        let pos = self
            .index
            .get(&h)?
            .iter()
            .copied()
            .find(|&i| value_eq(&self.entries[i].0, key))?;
        Some(&mut self.entries[pos].1)
    }

    pub fn insert(&mut self, key: Value, value: Value) {
        let h = Self::hash_key(&key);
        if let Some(bucket) = self.index.get(&h) {
            for &i in bucket {
                if value_eq(&self.entries[i].0, &key) {
                    self.entries[i].1 = value;
                    return;
                }
            }
        }
        let idx = self.entries.len();
        self.entries.push((key, value));
        self.index.entry(h).or_default().push(idx);
    }

    pub fn remove(&mut self, key: &Value) -> Option<Value> {
        let h = Self::hash_key(key);
        let pos = self.index.get(&h)?.iter().copied().find(|&i| value_eq(&self.entries[i].0, key))?;
        let (_, v) = self.entries.remove(pos);
        // rebuild index after positional removal
        self.index.clear();
        for (i, (k, _)) in self.entries.iter().enumerate() {
            self.index.entry(Self::hash_key(k)).or_default().push(i);
        }
        Some(v)
    }

    pub fn contains(&self, key: &Value) -> bool {
        self.get(key).is_some()
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn keys(&self) -> Vec<Value> {
        self.entries.iter().map(|(k, _)| k.clone()).collect()
    }
}

impl Value {
    pub fn int(v: i128, kind: IntKind) -> Value {
        Value::Int(kind.wrap(v), kind)
    }

    pub fn type_name(&self) -> String {
        match self {
            Value::Unit => "unit".into(),
            Value::Int(_, k) => k.name().into(),
            Value::Float(_, 32) => "float32".into(),
            Value::Float(..) => "float64".into(),
            Value::Bool(_) => "bool".into(),
            Value::Char(_) => "char".into(),
            Value::Str(_) => "str".into(),
            Value::Tuple(_) => "tuple".into(),
            Value::List(_) => "list".into(),
            Value::Map(_) => "map".into(),
            Value::Struct(s) => s.name.clone(),
            Value::Enum(e) => e.enum_name.clone(),
            Value::Closure(_) | Value::Func(_) | Value::Partial(_) | Value::Builtin(_) => {
                "function".into()
            }
            Value::Chan(_) => "chan".into(),
            Value::Task(_) => "task".into(),
            Value::Actor(a) => a.name.clone(),
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Value::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn display(&self) -> String {
        match self {
            Value::Unit => "()".into(),
            Value::Int(v, _) => v.to_string(),
            Value::Float(v, _) => format_float(*v),
            Value::Bool(b) => b.to_string(),
            Value::Char(c) => c.to_string(),
            Value::Str(s) => s.to_string(),
            Value::Tuple(xs) => {
                let inner: Vec<String> = xs.iter().map(|v| v.repr()).collect();
                format!("({})", inner.join(", "))
            }
            Value::List(xs) => {
                let inner: Vec<String> = xs.iter().map(|v| v.repr()).collect();
                format!("[{}]", inner.join(", "))
            }
            Value::Map(m) => {
                if m.is_empty() {
                    return "[:]".into();
                }
                let inner: Vec<String> =
                    m.entries.iter().map(|(k, v)| format!("{}: {}", k.repr(), v.repr())).collect();
                format!("[{}]", inner.join(", "))
            }
            Value::Struct(s) => {
                let inner: Vec<String> =
                    s.fields.iter().map(|(n, v)| format!("{}: {}", n, v.repr())).collect();
                format!("{} {{ {} }}", s.name, inner.join(", "))
            }
            Value::Enum(e) => {
                if e.payload.is_empty() {
                    e.variant.clone()
                } else {
                    let inner: Vec<String> = e.payload.iter().map(|v| v.repr()).collect();
                    format!("{}({})", e.variant, inner.join(", "))
                }
            }
            Value::Closure(_) | Value::Func(_) | Value::Partial(_) | Value::Builtin(_) => {
                "<function>".into()
            }
            Value::Chan(_) => "<chan>".into(),
            Value::Task(_) => "<task>".into(),
            Value::Actor(a) => format!("<actor {}>", a.name),
        }
    }

    /// Like `display`, but strings/chars are quoted (used inside aggregates).
    pub fn repr(&self) -> String {
        match self {
            Value::Str(s) => format!("\"{}\"", s),
            Value::Char(c) => format!("'{}'", c),
            _ => self.display(),
        }
    }
}

/// Structural equality used by `==` and as map-key equality.
pub fn value_eq(a: &Value, b: &Value) -> bool {
    use Value::*;
    match (a, b) {
        (Unit, Unit) => true,
        (Int(x, _), Int(y, _)) => x == y,
        (Float(x, _), Float(y, _)) => x == y,
        (Bool(x), Bool(y)) => x == y,
        (Char(x), Char(y)) => x == y,
        (Str(x), Str(y)) => x == y,
        (Tuple(x), Tuple(y)) | (List(x), List(y)) => {
            x.len() == y.len() && x.iter().zip(y.iter()).all(|(a, b)| value_eq(a, b))
        }
        (Map(x), Map(y)) => {
            x.len() == y.len()
                && x.entries.iter().all(|(k, v)| y.get(k).map(|w| value_eq(v, w)).unwrap_or(false))
        }
        (Struct(x), Struct(y)) => {
            x.name == y.name
                && x.fields.len() == y.fields.len()
                && x.fields.iter().zip(y.fields.iter()).all(|((_, a), (_, b))| value_eq(a, b))
        }
        (Enum(x), Enum(y)) => {
            x.enum_name == y.enum_name
                && x.variant == y.variant
                && x.payload.len() == y.payload.len()
                && x.payload.iter().zip(y.payload.iter()).all(|(a, b)| value_eq(a, b))
        }
        _ => false,
    }
}

impl PartialEq for Value {
    fn eq(&self, other: &Self) -> bool {
        value_eq(self, other)
    }
}
impl Eq for Value {}

impl Hash for Value {
    fn hash<H: Hasher>(&self, state: &mut H) {
        match self {
            Value::Unit => 0u8.hash(state),
            Value::Int(v, _) => {
                1u8.hash(state);
                v.hash(state);
            }
            Value::Float(v, _) => {
                2u8.hash(state);
                v.to_bits().hash(state);
            }
            Value::Bool(b) => {
                3u8.hash(state);
                b.hash(state);
            }
            Value::Char(c) => {
                4u8.hash(state);
                c.hash(state);
            }
            Value::Str(s) => {
                5u8.hash(state);
                s.hash(state);
            }
            Value::Tuple(xs) | Value::List(xs) => {
                6u8.hash(state);
                for v in xs.iter() {
                    v.hash(state);
                }
            }
            Value::Struct(s) => {
                7u8.hash(state);
                s.name.hash(state);
                for (_, v) in &s.fields {
                    v.hash(state);
                }
            }
            Value::Enum(e) => {
                8u8.hash(state);
                e.enum_name.hash(state);
                e.variant.hash(state);
                for v in &e.payload {
                    v.hash(state);
                }
            }
            Value::Map(m) => {
                9u8.hash(state);
                for (k, v) in &m.entries {
                    k.hash(state);
                    v.hash(state);
                }
            }
            _ => 255u8.hash(state),
        }
    }
}
