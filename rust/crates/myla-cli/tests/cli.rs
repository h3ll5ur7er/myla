//! End-to-end tests: example outputs, interpreter-vs-native differential
//! checks, and the negative (error) corpus.

use std::path::PathBuf;
use std::process::Command;

const BIN: &str = env!("CARGO_BIN_EXE_myla");

fn examples_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples")
}

fn example(name: &str) -> String {
    examples_dir().join(name).to_string_lossy().into_owned()
}

fn run_interp(path: &str) -> String {
    let out = Command::new(BIN)
        .args(["run", path])
        .output()
        .expect("spawn myla run");
    assert!(
        out.status.success(),
        "`run {path}` failed: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8(out.stdout).unwrap()
}

fn build_and_run_native(path: &str, tag: &str) -> String {
    let exe = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(tag);
    let exe = exe.to_string_lossy().into_owned();
    let build = Command::new(BIN)
        .args(["build", path, "-o", &exe])
        .output()
        .expect("spawn myla build");
    assert!(
        build.status.success(),
        "`build {path}` failed: {}",
        String::from_utf8_lossy(&build.stderr)
    );
    let out = Command::new(&exe).output().expect("run native exe");
    assert!(out.status.success(), "native `{tag}` exited non-zero");
    String::from_utf8(out.stdout).unwrap()
}

#[test]
fn example_outputs_match_expected() {
    let cases = [
        ("hello.my", "Hello from Myla (Rust edition)!\n"),
        ("fib.my", "0\n1\n1\n2\n3\n5\n8\n13\n21\n34\n"),
        ("floats.my", "5.0\n0.3333333333333333\n2\n"),
        ("enums.my", "12.56636\n12.0\n6\ndivide by zero\n"),
        ("collections.my", "10\nsomewhere\ntrue\ndiagonal\n"),
        ("concurrency.my", "3\n81\n3\n"),
    ];
    for (file, expected) in cases {
        let got = run_interp(&example(file));
        assert_eq!(got, expected, "interpreter output mismatch for {file}");
    }
}

#[test]
fn native_matches_interpreter() {
    // The native backend covers the scalar/control-flow/function/print core.
    for file in ["hello.my", "fib.my", "floats.my"] {
        let interp = run_interp(&example(file));
        let native = build_and_run_native(&example(file), &file.replace('.', "_"));
        assert_eq!(interp, native, "interpreter/native divergence for {file}");
    }
}

#[test]
fn inline_tests_pass() {
    for file in ["fib.my", "floats.my"] {
        let out = Command::new(BIN)
            .args(["test", &example(file)])
            .output()
            .expect("spawn myla test");
        assert!(
            out.status.success(),
            "`test {file}` failed: {}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
    }
}

#[test]
fn error_corpus_reports_expected_stage() {
    let dir = examples_dir().join("errors");
    for entry in std::fs::read_dir(&dir).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|e| e.to_str()) != Some("my") {
            continue;
        }
        let source = std::fs::read_to_string(&path).unwrap();
        let directive = source
            .lines()
            .find_map(|l| l.split("//~").nth(1))
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|| panic!("{path:?} has no //~ directive"));

        let out = Command::new(BIN)
            .args(["run", path.to_str().unwrap()])
            .output()
            .expect("spawn myla run");
        assert!(
            !out.status.success(),
            "{path:?} unexpectedly succeeded"
        );
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            stderr.contains(&directive),
            "{path:?}: expected stderr to contain {directive:?}, got:\n{stderr}"
        );
    }
}
