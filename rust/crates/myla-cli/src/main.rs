//! The `myla` command-line interface.

use std::process::ExitCode;

use clap::{Parser, Subcommand};
use myla_syntax::diagnostic::Diagnostic;

#[derive(Parser)]
#[command(name = "myla", version, about = "The Myla programming language (Rust implementation)")]
struct Cli {
    #[command(subcommand)]
    command: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Parse, type-check, and interpret a program.
    Run {
        file: String,
        /// Arguments forwarded to the program (available via `args()`).
        args: Vec<String>,
    },
    /// Compile a program to a native executable (Cranelift backend).
    Build {
        file: String,
        #[arg(short = 'o', long = "out", default_value = "a.out")]
        out: String,
    },
    /// Run the program's inline `#test(...)[...]` cases.
    Test { file: String },
    /// Print the token stream (debugging).
    Tokenize { file: String },
    /// Print the parsed AST (debugging).
    Parse { file: String },
    /// Start a simple read-eval-print loop.
    Repl,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match cli.command {
        Cmd::Run { file, args } => cmd_run(&file, args),
        Cmd::Build { file, out } => cmd_build(&file, &out),
        Cmd::Test { file } => cmd_test(&file),
        Cmd::Tokenize { file } => cmd_tokenize(&file),
        Cmd::Parse { file } => cmd_parse(&file),
        Cmd::Repl => cmd_repl(),
    }
}

fn read(file: &str) -> Result<String, ExitCode> {
    std::fs::read_to_string(file).map_err(|e| {
        eprintln!("error: cannot read `{file}`: {e}");
        ExitCode::FAILURE
    })
}

fn report(diags: &[Diagnostic], source: &str, file: &str) {
    for d in diags {
        eprintln!("{}\n", d.render(source, file));
    }
}

fn cmd_run(file: &str, args: Vec<String>) -> ExitCode {
    let source = match read(file) {
        Ok(s) => s,
        Err(c) => return c,
    };
    let program = match myla_syntax::parse_program(&source) {
        Ok(p) => p,
        Err(diags) => {
            report(&diags, &source, file);
            return ExitCode::FAILURE;
        }
    };
    let mut argv = vec![file.to_string()];
    argv.extend(args);
    match myla_interp::run(&program, argv) {
        Ok(code) => ExitCode::from(code as u8),
        Err(diags) => {
            report(&diags, &source, file);
            ExitCode::FAILURE
        }
    }
}

fn cmd_build(file: &str, out: &str) -> ExitCode {
    let source = match read(file) {
        Ok(s) => s,
        Err(c) => return c,
    };
    let program = match myla_syntax::parse_program(&source) {
        Ok(p) => p,
        Err(diags) => {
            report(&diags, &source, file);
            return ExitCode::FAILURE;
        }
    };
    let analyzed = match myla_sema::analyze(&program) {
        Ok(a) => a,
        Err(diags) => {
            report(&diags, &source, file);
            return ExitCode::FAILURE;
        }
    };
    match myla_codegen::build_executable(&program, &analyzed, out) {
        Ok(()) => {
            println!("wrote {out}");
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("build error: {e}");
            ExitCode::FAILURE
        }
    }
}

fn cmd_test(file: &str) -> ExitCode {
    let source = match read(file) {
        Ok(s) => s,
        Err(c) => return c,
    };
    let program = match myla_syntax::parse_program(&source) {
        Ok(p) => p,
        Err(diags) => {
            report(&diags, &source, file);
            return ExitCode::FAILURE;
        }
    };
    match myla_interp::run_tests(&program) {
        Ok((passed, failed, report)) => {
            print!("{report}");
            println!("{passed} passed, {failed} failed");
            if failed == 0 {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            }
        }
        Err(diags) => {
            report(&diags, &source, file);
            ExitCode::FAILURE
        }
    }
}

fn cmd_tokenize(file: &str) -> ExitCode {
    let source = match read(file) {
        Ok(s) => s,
        Err(c) => return c,
    };
    match myla_syntax::lexer::lex(&source) {
        Ok(tokens) => {
            for t in tokens {
                println!("{:?} {:?} {:?}", t.kind, t.span, t.text(&source));
            }
            ExitCode::SUCCESS
        }
        Err(diags) => {
            report(&diags, &source, file);
            ExitCode::FAILURE
        }
    }
}

fn cmd_parse(file: &str) -> ExitCode {
    let source = match read(file) {
        Ok(s) => s,
        Err(c) => return c,
    };
    match myla_syntax::parse_program(&source) {
        Ok(program) => {
            println!("{:#?}", program.items);
            ExitCode::SUCCESS
        }
        Err(diags) => {
            report(&diags, &source, file);
            ExitCode::FAILURE
        }
    }
}

fn cmd_repl() -> ExitCode {
    use std::io::{self, Write};
    println!("myla repl — type an expression-bodied program or `:quit`");
    let stdin = io::stdin();
    loop {
        print!("myla> ");
        let _ = io::stdout().flush();
        let mut line = String::new();
        if stdin.read_line(&mut line).unwrap_or(0) == 0 {
            break;
        }
        let line = line.trim();
        if line == ":quit" || line == ":q" {
            break;
        }
        if line.is_empty() {
            continue;
        }
        // Wrap the line in a main that prints the expression's value.
        let wrapped = format!("fun main() {{ print({line}) }}");
        match myla_syntax::parse_program(&wrapped) {
            Ok(program) => {
                if let Err(diags) = myla_interp::run(&program, vec!["repl".into()]) {
                    report(&diags, &wrapped, "<repl>");
                }
            }
            Err(diags) => report(&diags, &wrapped, "<repl>"),
        }
    }
    ExitCode::SUCCESS
}
