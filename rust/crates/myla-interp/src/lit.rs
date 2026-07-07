//! Parsing of integer/float literal text into runtime values.

use myla_runtime::IntKind;

/// Parse an integer literal (with optional base prefix, `_` separators, and
/// `iN`/`uN` suffix). Returns the value and its kind (default `int32`).
pub fn parse_int(text: &str) -> (i128, IntKind) {
    let (body, kind) = split_int_suffix(text);
    let clean: String = body.chars().filter(|c| *c != '_').collect();
    let value = if let Some(hex) = clean.strip_prefix("0x").or_else(|| clean.strip_prefix("0X")) {
        i128::from_str_radix(hex, 16).unwrap_or(0)
    } else if let Some(bin) = clean.strip_prefix("0b").or_else(|| clean.strip_prefix("0B")) {
        i128::from_str_radix(bin, 2).unwrap_or(0)
    } else if let Some(oct) = clean.strip_prefix("0o").or_else(|| clean.strip_prefix("0O")) {
        i128::from_str_radix(oct, 8).unwrap_or(0)
    } else {
        clean.parse::<i128>().unwrap_or(0)
    };
    (kind.wrap(value), kind)
}

fn split_int_suffix(text: &str) -> (&str, IntKind) {
    for (suffix, kind) in [
        ("i8", IntKind::I8),
        ("i16", IntKind::I16),
        ("i32", IntKind::I32),
        ("i64", IntKind::I64),
        ("u8", IntKind::U8),
        ("u16", IntKind::U16),
        ("u32", IntKind::U32),
        ("u64", IntKind::U64),
    ] {
        if let Some(body) = text.strip_suffix(suffix) {
            return (body, kind);
        }
    }
    (text, IntKind::I32)
}

/// Parse a float literal (with optional `fN` suffix). Returns value + bit width.
pub fn parse_float(text: &str) -> (f64, u8) {
    let (body, bits) = if let Some(b) = text.strip_suffix("f32") {
        (b, 32)
    } else if let Some(b) = text.strip_suffix("f64") {
        (b, 64)
    } else {
        (text, 64)
    };
    let clean: String = body.chars().filter(|c| *c != '_').collect();
    let v = clean.parse::<f64>().unwrap_or(0.0);
    let v = if bits == 32 { v as f32 as f64 } else { v };
    (v, bits)
}
