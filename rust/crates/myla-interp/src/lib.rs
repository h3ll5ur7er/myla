//! Tree-walking interpreter — the reference semantics of Myla.

mod control;
mod env;
mod interp;
mod lit;
mod value;

use std::sync::Arc;

use myla_syntax::ast::Program;
use myla_syntax::diagnostic::{Diagnostic, Stage};

pub use control::RuntimeError;
pub use interp::Interp;
pub use value::Value;

/// Analyze + run a program, returning its exit code.
pub fn run(program: &Program, args: Vec<String>) -> Result<i32, Vec<Diagnostic>> {
    let analyzed = myla_sema::analyze(program)?;
    let interp = Interp::new(Arc::new(analyzed), args);
    interp.run().map_err(|e| vec![runtime_diag(e)])
}

/// Run the `#test` cases collected during analysis. Returns (passed, failed, report).
pub fn run_tests(program: &Program) -> Result<(usize, usize, String), Vec<Diagnostic>> {
    let analyzed = Arc::new(myla_sema::analyze(program)?);
    let interp = Interp::new(analyzed.clone(), Vec::new());
    let mut passed = 0;
    let mut failed = 0;
    let mut report = String::new();
    for case in &analyzed.tests {
        let args: Result<Vec<Value>, _> = case
            .args
            .iter()
            .map(|e| interp.eval_const_expr(e))
            .collect();
        let expected = interp.eval_const_expr(&case.expected);
        match (args, expected) {
            (Ok(args), Ok(expected)) => match interp.eval_call_named(&case.func, args) {
                Ok(got) if got == expected => passed += 1,
                Ok(got) => {
                    failed += 1;
                    report.push_str(&format!(
                        "FAIL {}: expected {}, got {}\n",
                        case.func,
                        expected.display(),
                        got.display()
                    ));
                }
                Err(_) => {
                    failed += 1;
                    report.push_str(&format!("FAIL {}: runtime error\n", case.func));
                }
            },
            _ => {
                failed += 1;
                report.push_str(&format!("FAIL {}: could not evaluate case\n", case.func));
            }
        }
    }
    Ok((passed, failed, report))
}

fn runtime_diag(e: RuntimeError) -> Diagnostic {
    Diagnostic::error(
        Stage::Runtime,
        e.message,
        e.span.unwrap_or(myla_syntax::span::Span::DUMMY),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn run_src(src: &str) -> i32 {
        let program = myla_syntax::parse_program(src).expect("parse");
        run(&program, Vec::new()).expect("run")
    }

    #[test]
    fn arithmetic_and_print() {
        // Just ensure it runs without error; stdout checked in CLI integration tests.
        assert_eq!(run_src("fun main() { let x = 2 + 3 * 4; print(x) }"), 0);
    }

    #[test]
    fn floats_and_casts() {
        assert_eq!(
            run_src("fun main() { let x = 3.0 / 2.0; print(x); print(7 as float) }"),
            0
        );
    }

    #[test]
    fn structs_enums_match() {
        let src = r#"
enum Shape { Circle(float), Square(float) }
fun area(s: Shape) -> float {
    match s {
        Shape.Circle(r) => 3.14159 * r * r,
        Shape.Square(a) => a * a,
    }
}
fun main() {
    let c = Shape.Circle(2.0)
    print(area(c))
}
"#;
        assert_eq!(run_src(src), 0);
    }

    #[test]
    fn collections_and_loops() {
        let src = r#"
fun main() {
    var xs = [1, 2, 3]
    xs.push(4)
    var total = 0
    for x in xs { total = total + x }
    print(total)
    var m = ["a": 1]
    m["b"] = 2
    print(m.contains("b"))
}
"#;
        assert_eq!(run_src(src), 0);
    }

    #[test]
    fn closures_and_pipeline() {
        let src = r#"
fun twice(f: (int) -> int, x: int) -> int { return f(f(x)) }
fun main() {
    let inc = (x: int) => x + 1
    print(twice(inc, 10))
    print([1, 2, 3] |> len)
}
"#;
        assert_eq!(run_src(src), 0);
    }

    #[test]
    fn result_and_question() {
        let src = r#"
fun checked(n: int) -> Result<int, str> {
    if n < 0 { return Err("negative") }
    return Ok(n * 2)
}
fun use_it(n: int) -> Result<int, str> {
    let v = checked(n)?
    return Ok(v + 1)
}
fun main() {
    match use_it(5) {
        Ok(v) => print(v),
        Err(e) => print(e),
    }
}
"#;
        assert_eq!(run_src(src), 0);
    }

    #[test]
    fn concurrency_channels() {
        let src = r#"
fun main() {
    let ch = make_chan()
    spawn { ch.send(42) }
    let v = ch.recv()
    print(v)
}
"#;
        assert_eq!(run_src(src), 0);
    }

    #[test]
    fn mutability_error_is_caught() {
        let program = myla_syntax::parse_program("fun main() { let x = 1\n x = 2 }").unwrap();
        let result = run(&program, Vec::new());
        assert!(result.is_err());
    }

    fn _silence_write(_w: &mut impl Write) {}
}
