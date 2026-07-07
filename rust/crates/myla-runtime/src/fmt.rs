//! Shared value formatting helpers.

/// Format a float as a round-trippable decimal, always showing a fractional part
/// (so `2.0` prints as `2.0`, not `2`).
pub fn format_float(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    if v.is_infinite() {
        return if v < 0.0 { "-inf".into() } else { "inf".into() };
    }
    let mut buf = ryu::Buffer::new();
    buf.format(v).to_string()
}
