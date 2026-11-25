"""Burn tests: run each example program and assert its stdout.

These pin down end-to-end behavior (lexer -> parser -> checker -> interpreter)
and double as living documentation of what each example prints. The
self-hosted interpreter (`myla run`) runs them; the table is the expectation
(it was checked with the Python interpreter until MYLA-219).
"""
import os
import unittest

from tests.burn._native import selfhost_run

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples")
)

# filename -> expected stdout
EXPECTED = {
    "hello.my": "Hello from Myla!\n",
    "variables.my": "10\nAnn\ntrue\n2\n",
    "functions.my": "5\n120\n120\ntrue\n",
    "loops.my": "10\n3\n2\n1\ntrue\n",
    "control_flow.my": "negative\nzero\npositive\ntrue\ntrue\ntrue\n",
    "structs.my": "3\n4\n7\n100\n3\n",
    "attributes.my": "5\n0\n",
    "tuples.my": "7\nseven\n42\n3\n2\n6\n100\n15\n25\n5\n",
    "unicode.my": "6\n6\u20ac\n{6}\n3\ntrue\n\"\nit's \U0001F600\n",
    "enums.my": "12\n12\n0\nwarm\ncool\nbig circle\nsmall circle\nother\n",
    "types_and_aliases.my": "0\n42\n9\n",
    "recursion.my": "6\n6\n3\n12\n10\n10\nbalanced pair\nbranch\n",
    "regressions.my": "zero\n5\n5\nminus one\n1\n",
    "generics.my": "42\nmyla\n10\n2\n1\n16\n",
    "generic-types.my": "42\n1\n9\n-1\n60\n3\n",
    "option-result.my": "ok\ndivide by zero\n107\n-1\n42\n",
    "operators.my": "255\n8\n14\n6\n255\n16\n-8\n15\n1\n-56\n30\n11\n",
    "constants.my": "4096\n4096\n255\ntrue\n64\n2\n5\nmyla\n",
    "lists.my": "3\n1\n6\n6\n10\n3\n99\n4\n20\n5\n6\n16\n16\n4\n",
    "maps.my": "6\n2\n3\n3\n1\n10\n4\n3\nfalse\ntrue\n3\n17\n100\n2\n",
    "strings.my": ("4\n77\n97\n5\n98\n3\n198\n10\n1\n1\n0\n"
                   "Hello, world!\nabc\n2 + 3 = 5\nlen: 5\ntrue and false\n"
                   "Hello, world!\n0123456789\na-b-c\n"),
    "methods.my": "1\n2\n12\n12\nfalse\n10\ntrue\n42\n4\n",
    "closures.my": ("36\n15\nhi, world\n24\n16\n18\n107\n60\n"
                    "6\n100\n42\n"),
    "pipelines.my": "11\n8\n21\n14\n15\n42\n18\n11\n12\n20\n",
    "traits.my": "4\n6\ntrue\ntrue\nvec\ntrue\nfalse\ntrue\ntrue\n60\n3\n4\n8\n3\n",
    "floats.my": ("0.5\n3.141592653589793\n3.75\n3.5\n1.5\n-3.141592653589793\n"
                  "0.30000000000000004\n0.3\ninf\ntrue\nfalse\n9\n3\n3\n"),
    "chars.my": "a\nλ\n😀\ntrue\nfalse\n65\nλ\ntrue\n2\n1\n5\n3\n104\n233\n955\n",
    "generic_traits.my": "0\n1\n-1\n0\n1\n-1\n",
    "iterators.my": "3\n2\n1\n15\n30\n7\n3\n",
    "trait_functions.my": "0\n400\n9\n17\n60\n-1\n",
    "interpolation.my": ("myla scored 42\n2 + 3 = 5\nset is { 1, 2 }\n"
                         "main.my:3:12: there is no error, this is just a test\n"),
    "traits_on_builtins.my": ("49\nhaha 67\n42\nI'm a teapot\nThis is not the error you are looking for. It is the answer to life, the universe, and everything.\nThis is not the error you are looking for. It is 13\nThis is not the error you are looking for. It is 15\nSuccess\n"),
    "semicolons.my": "12\nsize\n7\n15\n21\n42\n",
    "concurrency.my": "40\n30\n200\ntrue\nfalse\n150\n50\n31\n",
    # the November features (MYLA-299)
    "slices_and_formats.my": ("50\n3\n30\nalym\n3.14 [   42] [007] 0xff\n19.99 or about 19\n"
                              "0.30000000000000004\n0.25\n"),
    "branches_and_defaults.my": ("2\npositive\n3\nport 443\nbad port: not a digit: x\n"
                                 "Hello, Myla!\nHello, Myla?\n2\n1\nlift-off\n"),
    "time_and_math.my": "1.41\ntrue\n3.141592653589793\nanswered 7\ngave up\n7\ntrue\n",
    "transforms.my": "(243, 275)\n(320, 249)\n(235, 164)\n(320, 154)\n(320, 312)\n(397, 275)\n(320, 179)\n(405, 164)\ntrue\n",
    "images.my": ("::::::::::::::::\n----------------\n---------%%%%%--\n=========%%%%%==\n=========%%%%%==\n"
                  "+++++++++%%%%%++\n+++++++++%%%%%++\n****************\n****************\n################\n"
                  "................\n................\n................\n................\n................\n"
                  "................\ncorner 8x8, top left #b8979cff\n"
                  "palette #122f6eff #6b6aa3ff #eac07dff #af929dff\n0100100100100100\n1010101010101011\n"
                  "1111011102222210\n1101111112222211\n1111111112222211\n1111111112222233\n3333333332222233\n"
                  "3333333333222233\n3232332323233323\n2223223223222232\n0000000000000000\n0000000000000000\n"
                  "0000000000000000\n0000000000000000\n0000000000000000\n0000000000000000\n"
                  "preview: 8 lines of 16 cells\n"),
    "book_api.my": 'GET /api/books/2 -> 200 {"id":2,"title":"The Dispossessed","year":1974} (version 1)\nGET /api/books/search?q=dark -> 200 {"query":"dark","found":[{"id":1,"title":"The Left Hand of Darkness","year":1969}]} (version 1)\nGET /api/books/9 -> 404 {"error":"no book 9"} (version 1)\nPOST /api/books -> 200 {"id":4,"title":"The Lathe of Heaven","year":1971} (version 1)\nPOST /api/books -> 422 {"error":"$.title: missing field"} (version 1)\nDELETE /api/books/2 -> 405 method not allowed (version 1)\nGET / -> 200 see /api/books/{id} (version -)\n',
    "binary_data.my": "24 bytes\nNAME: 4 bytes\nCODE: 4 bytes\ntrue\ncut short\n",
    "lzw_and_packbits.my": ("GIF LZW: 256 bytes in 72, 74 as sub-blocks\ndecoded: true\nTIFF LZW: 110 bytes\n"
                            "at most 100 bytes: output longer than max_output\nPackBits: 201 bytes\n"
                            "one byte short: compressed data ends too early\n"),
    "gif_animation.my": (
        '187 bytes, 4 frames of 20x8\n'
        'loops 0 (0: forever)\n'
        'frame at (0, 0), 20x8, 120 ms, Keep\n'
        'frame at (1, 3), 5x3, 120 ms, Keep\n'
        'frame at (3, 3), 5x3, 120 ms, Keep\n'
        'frame at (5, 3), 5x3, 120 ms, Keep\n'
        'shown as made: true\n'
        '....................\n'
        '....................\n'
        '....................\n'
        '.......@@@..........\n'
        '.......@@@..........\n'
        '.......@@@..........\n'
        '==--==--==--==--==--\n'
        '==--==--==--==--==--\n'
        'info: 20x8, 4 frames\n'
    ),
    "image_files.my": ("PAM: 578 bytes, read back: the same\nPPM: 396 bytes, read back: the same\n"
                       "BMP, 32 bits: 634 bytes, read back: the same\nBMP, 24 bits: 438 bytes, read back: the same\n"
                       "QOI: 274 bytes, read back: the same\nbmp: 16x8 rgba, 8 bits a sample\n"
                       "P2\n4 2\n255\n194 178 162 146\n76 61 45 29\nQOI cut short: 20 bytes, read back: truncated input\n"),
    "png_badge.my": ("drawn: 48x20 rgba, pixels 64c3d222\nPNG: 441 bytes, 48x20 rgba, 8 bits\n"
                      "decoded back the same: true\npalette PNG: 13 colours, 279 bytes, 48x20 rgba, 4 bits\n"
                      "the same pixels: true\nerror: checksum mismatch\n"),
    "tiff_files.my": ('none      37096 bytes, read back the same: true\n'
                      'PackBits  37408 bytes, read back the same: true\n'
                      'LZW        2980 bytes, read back the same: true\n'
                      'Deflate    1108 bytes, read back the same: true\n'
                      '1 page: 96x64 rgb, 16 bits\n'
                      '  ImageWidth: 96\n'
                      '  ImageLength: 64\n'
                      '  BitsPerSample: 16, 16, 16\n'
                      '  Compression: 5\n'
                      '  PhotometricInterpretation: 2\n'
                      '  SamplesPerPixel: 3\n'
                      '  RowsPerStrip: 14\n'
                      '  XResolution: 72/1\n'
                      '  YResolution: 72/1\n'
                      '  PlanarConfiguration: 1\n'
                      '  ResolutionUnit: 2\n'
                      '  Predictor: 2\n'
                      '8 bits: pixel (48, 0) is #4000bfff\n'
                      'not a TIFF: unsupported: CMYK\n'),
    "draw_chart.my": (
        '                                                \n'
        '          @@@@  @@@  @     @@@@@  @@@@          \n'
        '         @     @   @ @     @     @              \n'
        '         @     @   @ @     @     @              \n'
        '          @@@  @@@@@ @     @@@@   @@@           \n'
        '             @ @   @ @     @         @          \n'
        '             @ @   @ @     @         @          \n'
        '         @@@@  @   @ @@@@@ @@@@@ @@@@           \n'
        '                                                \n'
        '                                                \n'
        '                                         .=.    \n'
        '   @                                    =%%.    \n'
        '   @                        ..        :#%#=--   \n'
        '   @                       +@@%*-.  .*@#-----   \n'
        '   @                     :%%+=*#@@%*%%- .----   \n'
        '   @          :.        +%#=--- .-+#+   .----   \n'
        '   @        =#@@%*-.  :#%=:----  .::::  .----   \n'
        '   @     .+%@#==*#@@%*%#: .----  .----  .----   \n'
        '   @   :*%%+----- .-+#+   .----  .----  .----   \n'
        '   @   *#=  .----  .::::  .----  .----  .----   \n'
        '   @ .::::  .----  .----  .----  .----  .----   \n'
        '   @ .----  .----  .----  .----  .----  .----   \n'
        '   @ .----  .----  .----  .----  .----  .----   \n'
        '   @ .----  .----  .----  .----  .----  .----   \n'
        '   @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ \n'
        '                                                \n'
    ),
    "edges.my": (
        "........................................\n"
        "........................................\n"
        "........................................\n"
        ".........###............############....\n"
        "......###...###.........#..........#....\n"
        ".....##.......##.......#...........#....\n"
        ".....#.........#........#..........#....\n"
        ".....#.........#........############....\n"
        "....#...........#.......................\n"
        "....#...........#.......................\n"
        "....#...........#.......................\n"
        ".....#.........#........................\n"
        ".....#.........#........................\n"
        ".....##.......##........................\n"
        "......#########.........................\n"
        "........................................\n"
        "........................................\n"
        "threshold 39: 2 shapes\n"
        "  113 pixels in 13x13 at (4, 3), centre (10.0, 9.0)\n"
        "  60 pixels in 12x5 at (24, 3), centre (29.5, 5.0)\n"
        "|   ..:......::::::..|\n"
        "|  -#%%%*....++++++..|\n"
        "|  +%%%%%............|\n"
        "|  .=+++:............|\n"
    ),
    "font_text.my": 'Myla Test Sans Regular: 176 glyphs, 2048 units to the em\n'
        "'Hello, Myla!' at 16 px: 83.58 by 17.88 px\n"
        'V after A: 9.48 px kerned, 10.67 px not\n'
        'a paragraph at 12 px: 2 lines, 142.73 by 27.21 px\n'
        '                                                            \n'
        '                                                            \n'
        '                                                            \n'
        '                             =-                             \n'
        '  :**.       -**             %#                             \n'
        '  -@@+       #@@             %#                             \n'
        '  -@#%      :@#@             %#                             \n'
        '  -@=@-     +%+@  +-     .+- %#    -+*+-         +-     .+- \n'
        '  -@:%*     %++@  #%     =@: %#   #%*+*@#        #%     =@: \n'
        '  -@:+%.   -@:+@  -@=    #%  %#  =@-   +@-       -@=    #%  \n'
        '  -@:.@=   *# +@   %#   .@=  %#   .    :@=        %#   .@=  \n'
        '  -@: ##  .%= +@   +@:  =@.  %#    .---+@+        +@:  =@.  \n'
        '  -@: -@: =%  +@   .@+  #*   %#  .#@%###@+        .@+  #*   \n'
        '  -@:  %+ #*  +@    #% :@-   %#  #%-   :@+         #% :@-   \n'
        '  -@:  +%:@-  +@    -@:+%    %#  @*    -@+         -@:+%    \n'
        '  -@:  :@*%   +@     %*%+    %#  @*    #@+          %*%+    \n'
        '  -@:   #@+   +@     +%@:    %#  #%-.:#=@#.         +%@:    \n'
        '  -@:   =@.   +@     .@#     %#  .#@@%= +@%.        .@#     \n'
        '                     :@-           ..               :@-     \n'
        '                     *%                             *%      \n'
        '                  .:*@-                          .:*@-      \n'
        '                  +@%=                           +@%=       \n'
        '                   .                              .         \n'
        '5 glyphs drawn, 4 masks rasterised\n',
    "page_scan.my": "threshold 134: 1 outline of 227 pixels, simplified to 4 corners\n"
        "  corner (13, 9), true (14, 9)\n"
        "  corner (88, 14), true (88, 15)\n"
        "  corner (81, 55), true (80, 55)\n"
        "  corner (9, 48), true (9, 47)\n"
        "....................................\n"
        "....................................\n"
        "....................................\n"
        "......#...#.#...#.#......###........\n"
        "......##.##.#...#.#.....#...#.......\n"
        "......#.#.#..#.#..#.....#...#.......\n"
        "......#.#.#...#...#.....#####.......\n"
        "......#...#...#...#.....#...#.......\n"
        "......#...#...#...#.....#...#.......\n"
        "......#...#...#...#####.#...#.......\n"
        "....................................\n"
        "....................................\n"
        "....................................\n"
        "......########################......\n"
        "....................................\n"
        "....................................\n"
        "against the page drawn: PSNR 18.7 dB\n",
}

def run_file(path: str) -> str:
    """What `myla run path` prints; it must succeed without diagnostics."""
    out, err, code = selfhost_run(path)
    assert (err, code) == ("", 0), f"myla run {os.path.basename(path)} failed ({code}):\n{err}"
    return out


def _example_files() -> set[str]:
    return {f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".my")}


class TestExamplesRun(unittest.TestCase):
    def test_every_example_has_expected_output(self):
        # Convention: every example is pinned by its expected stdout here, so a
        # new feature example can't land without run coverage.
        missing = _example_files() - set(EXPECTED)
        self.assertFalse(missing, f"examples without expected output: {sorted(missing)}")

    def test_no_stale_expectations(self):
        stale = set(EXPECTED) - _example_files()
        self.assertFalse(stale, f"expected output for missing examples: {sorted(stale)}")


def _make(name: str, expected: str):
    def test(self):
        path = os.path.join(EXAMPLES_DIR, name)
        self.assertTrue(os.path.exists(path), f"missing example {name}")
        self.assertEqual(run_file(path), expected)
    return test


for _name, _expected in EXPECTED.items():
    setattr(TestExamplesRun, f"test_{_name.replace('.', '_')}", _make(_name, _expected))


if __name__ == "__main__":
    unittest.main()
