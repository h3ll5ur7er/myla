//! Sized-integer kinds and wrapping arithmetic, shared by interpreter and codegen.

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct IntKind {
    pub bits: u8,
    pub signed: bool,
}

impl IntKind {
    pub const I8: IntKind = IntKind { bits: 8, signed: true };
    pub const I16: IntKind = IntKind { bits: 16, signed: true };
    pub const I32: IntKind = IntKind { bits: 32, signed: true };
    pub const I64: IntKind = IntKind { bits: 64, signed: true };
    pub const U8: IntKind = IntKind { bits: 8, signed: false };
    pub const U16: IntKind = IntKind { bits: 16, signed: false };
    pub const U32: IntKind = IntKind { bits: 32, signed: false };
    pub const U64: IntKind = IntKind { bits: 64, signed: false };

    /// Resolve a type name (`int`, `int8`, `uint64`, ...) to a kind.
    pub fn from_name(name: &str) -> Option<IntKind> {
        Some(match name {
            "int" | "int32" => IntKind::I32,
            "int8" => IntKind::I8,
            "int16" => IntKind::I16,
            "int64" => IntKind::I64,
            "uint8" => IntKind::U8,
            "uint16" => IntKind::U16,
            "uint32" => IntKind::U32,
            "uint64" => IntKind::U64,
            _ => return None,
        })
    }

    pub fn name(&self) -> &'static str {
        match (self.bits, self.signed) {
            (8, true) => "int8",
            (16, true) => "int16",
            (32, true) => "int32",
            (64, true) => "int64",
            (8, false) => "uint8",
            (16, false) => "uint16",
            (32, false) => "uint32",
            (64, false) => "uint64",
            _ => "int",
        }
    }

    /// Wrap a wide value into this kind's range (two's-complement / modular).
    pub fn wrap(&self, v: i128) -> i128 {
        if self.bits == 64 {
            if self.signed {
                v as i64 as i128
            } else {
                v as u64 as i128
            }
        } else {
            let mask: i128 = (1i128 << self.bits) - 1;
            let m = v & mask;
            if self.signed && (m & (1i128 << (self.bits - 1))) != 0 {
                m - (1i128 << self.bits)
            } else {
                m
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wraps_signed_and_unsigned() {
        assert_eq!(IntKind::I8.wrap(255), -1);
        assert_eq!(IntKind::U8.wrap(256), 0);
        assert_eq!(IntKind::I32.wrap(i128::from(i32::MAX) + 1), i128::from(i32::MIN));
        assert_eq!(IntKind::U64.wrap(-1), i128::from(u64::MAX));
    }
}
