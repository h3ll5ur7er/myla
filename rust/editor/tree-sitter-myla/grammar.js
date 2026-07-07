/**
 * tree-sitter grammar for Myla (Rust edition).
 *
 * This is editor-tooling only — it is intentionally kept OFF the compiler path
 * (the real parser is the hand-written one in `crates/myla-syntax`). It aims for
 * good highlighting/structure, not perfect disambiguation.
 *
 * Build with the tree-sitter CLI:  `tree-sitter generate && tree-sitter test`.
 */

module.exports = grammar({
  name: 'myla',

  extras: $ => [/\s/, $.line_comment, $.block_comment],

  word: $ => $.identifier,

  // The grouped-expression / tuple / lambda-parameter forms all begin with
  // `(` and overlap on identifiers and `self`. Resolving which one applies
  // requires looking ahead to `=>` (lambda) vs `)` (group/tuple), so we let
  // tree-sitter's GLR explore both interpretations.
  conflicts: $ => [
    [$.param, $._expr],
  ],

  rules: {
    source_file: $ => repeat($._item),

    line_comment: _ => token(seq('//', /[^\n]*/)),
    block_comment: _ => token(seq('/*', /[^*]*\*+([^/*][^*]*\*+)*/, '/')),

    _item: $ => seq(
      repeat($.attribute),
      optional('pub'),
      choice(
        $.function,
        $.struct,
        $.enum,
        $.trait,
        $.impl,
        $.actor,
        $.typealias,
        $.const,
        $.import,
      ),
    ),

    attribute: $ => seq(
      '#', $.identifier,
      optional(seq('(', optional($._expr_list), ')')),
      optional(seq('[', optional($._expr_list), ']')),
    ),

    function: $ => seq(
      optional('async'), 'fun', field('name', $.identifier),
      optional($.generics), $.params,
      optional(seq('->', $._type)),
      $.block,
    ),

    generics: $ => seq('<', commaSep1($.generic_param), '>'),
    generic_param: $ => seq($.identifier, optional(seq(':', sep1('+', $.identifier)))),

    params: $ => seq('(', optional(commaSep1($.param)), ')'),
    param: $ => choice(
      seq(optional('var'), 'self'),
      seq($.identifier, optional(seq(':', $._type))),
    ),

    struct: $ => seq('struct', $.identifier, optional($.generics),
      '{', repeat(seq($.field, optional(choice(',', '\n')))), '}'),
    field: $ => seq($.identifier, ':', $._type),

    enum: $ => seq('enum', $.identifier, optional($.generics),
      '{', repeat(seq($.variant, optional(choice(',', '\n')))), '}'),
    variant: $ => seq($.identifier, optional(seq('(', commaSep1($._type), ')'))),

    trait: $ => seq('trait', $.identifier, optional($.generics), '{', repeat($.function), '}'),
    impl: $ => seq('impl', optional($.generics), $._type, optional(seq('for', $._type)),
      '{', repeat(seq(optional('pub'), $.function)), '}'),
    actor: $ => seq('actor', $.identifier, '{', repeat(choice($.field, $.function)), '}'),

    typealias: $ => seq('typealias', $.identifier, '=', $._type),
    const: $ => seq('const', $.identifier, ':', $._type, '=', $._expr),
    import: $ => choice(
      seq('import', $.dotted_path, optional(seq('as', $.identifier))),
      seq('from', $.dotted_path, 'import', commaSep1($.identifier)),
    ),
    dotted_path: $ => sep1('.', $.identifier),

    _type: $ => choice(
      $.named_type,
      $.tuple_type,
      $.list_or_map_type,
      $.chan_type,
      'self',
    ),
    named_type: $ => seq($.identifier, optional(seq('<', commaSep1($._type), '>'))),
    tuple_type: $ => seq('(', optional(commaSep1($._type)), ')', optional(seq('->', $._type))),
    list_or_map_type: $ => seq('[', $._type, optional(seq(':', $._type)), ']'),
    chan_type: $ => seq('chan', '<', $._type, '>'),

    block: $ => seq('{', repeat($._statement), '}'),

    _statement: $ => choice(
      $.let_statement,
      $.return_statement,
      $.while_statement,
      $.for_statement,
      'break',
      'continue',
      $.assignment,
      $._expr,
    ),
    let_statement: $ => seq(choice('let', 'var'), $.identifier,
      optional(seq(':', $._type)), '=', $._expr),
    return_statement: $ => prec.right(seq('return', optional($._expr))),
    while_statement: $ => seq('while', $._expr, $.block),
    for_statement: $ => seq('for', $.identifier, 'in', $._expr, $.block),
    assignment: $ => seq($._expr, '=', $._expr),

    _expr: $ => choice(
      $.integer, $.float, $.string, $.fstring, $.char, $.boolean,
      $.identifier, 'self',
      $.unary, $.binary, $.call, $.index, $.field_access,
      $.list, $.map, $.tuple, $.lambda,
      $.if_expr, $.match_expr, $.block,
      $.spawn_expr, $.await_expr,
      seq('(', $._expr, ')'),
    ),

    unary: $ => prec(11, seq(choice('-', '!', '~'), $._expr)),
    binary: $ => choice(
      ...[
        ['||', 1], ['&&', 2], ['==', 3], ['!=', 3],
        ['<', 4], ['<=', 4], ['>', 4], ['>=', 4],
        ['|', 5], ['^', 6], ['&', 7],
        ['+', 9], ['-', 9], ['*', 10], ['/', 10], ['%', 10],
        ['|>', 0],
      ].map(([op, p]) => prec.left(p, seq($._expr, op, $._expr))),
    ),
    call: $ => prec(12, seq($._expr, '(', optional($._expr_list), ')')),
    index: $ => prec(12, seq($._expr, '[', $._expr, ']')),
    field_access: $ => prec(12, seq($._expr, '.', $.identifier)),
    lambda: $ => prec.right(-1, seq($.params, '=>', $._expr)),

    list: $ => seq('[', optional($._expr_list), ']'),
    map: $ => seq('[', choice(':', commaSep1(seq($._expr, ':', $._expr))), ']'),
    tuple: $ => seq('(', $._expr, ',', optional($._expr_list), ')'),

    if_expr: $ => prec.right(seq('if', $._expr, $.block,
      optional(seq('else', choice($.if_expr, $.block))))),
    match_expr: $ => seq('match', $._expr, '{', repeat($.match_arm), '}'),
    match_arm: $ => seq($._expr, optional(seq('if', $._expr)), '=>', $._expr, optional(',')),

    spawn_expr: $ => prec.right(seq(choice('spawn', 'go'), $._expr)),
    await_expr: $ => prec.right(seq('await', $._expr)),

    _expr_list: $ => commaSep1($._expr),

    integer: _ => token(/[0-9][0-9_]*([iu](8|16|32|64))?|0x[0-9a-fA-F_]+|0b[01_]+|0o[0-7_]+/),
    float: _ => token(/[0-9][0-9_]*\.[0-9_]+([eE][+-]?[0-9_]+)?(f32|f64)?/),
    string: _ => token(seq('"', /([^"\\]|\\.)*/, '"')),
    fstring: _ => token(seq('f"', /([^"\\]|\\.)*/, '"')),
    char: _ => token(seq("'", /([^'\\]|\\.)/, "'")),
    boolean: _ => choice('true', 'false'),
    identifier: _ => /[A-Za-z_][A-Za-z0-9_]*/,
  },
});

function commaSep1(rule) { return seq(rule, repeat(seq(',', rule)), optional(',')); }
function sep1(s, rule) { return seq(rule, repeat(seq(s, rule))); }
