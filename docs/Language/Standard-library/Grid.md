# std.grid

`Grid<T>`, a two-dimensional array of cells with a width and a height ([[MYLA-342]]). It reads a grid from text and prints it back, reaches a cell by its position with a bounds check, and gives the 4 or 8 neighbours of a cell. The searches of [[Language/Standard-library/Graph]] take it as their graph. The module imports std.list and std.option.

```myla
import std.grid as grid
from std.grid import Grid

fun main() {
    var g = grid.parse("#.##\n#..#\n##.#\n").expect("a grid")
    print(f"{g.width} by {g.height}")
    print(g.at((1, 1)).unwrap_or('?'))
    print(g.at((9, 9)).unwrap_or('?'))
    var open = 0
    for p in g.neighbours8((1, 1)) {
        if g.at(p).unwrap_or('#') == '.' {
            open += 1
        }
    }
    print(open)
    g.set((2, 2), 'o')
    print(g.text())
    let (x, y) = g.find('o').unwrap_or((-1, -1))
    print(f"o at {x},{y}, cell {g.index((x, y))}")
    let digits: Grid<int> = grid.parse_with("123\n456", (c) => c - '0').expect("digits")
    print(digits.column(2).map((d) => f"{d}").join(" "))
    print(digits.transposed().text())
    match grid.parse("ab\nc") {
        Ok(_) => print("a grid")
        Err(e) => print(e)
    }
}
// output:
// 4 by 3
// .
// ?
// 3
// #.##
// #..#
// ##o#
// o at 2,2, cell 10
// 3 6
// 14
// 25
// 36
// row 2 has 1 cell, row 1 has 2
```

| Function | Result |
| --- | --- |
| `new<T>(width: int, height: int, fill: T) -> Grid<T>` | A grid of `width` by `height` cells, each `fill`. A negative size, or more than 2147483647 cells, is a failure (D184) |
| `of<T>(rows: [[T]]) -> Result<Grid<T>, GridError>` | The grid of `rows`, `rows[y][x]` the cell at `(x, y)`; `Ragged` if a row has another length than the first |
| `parse(text: str) -> Result<Grid<char>, GridError>` | The grid of the characters of `text`, a line a row |
| `parse_with<T>(text: str, f: (char) -> T) -> Result<Grid<T>, GridError>` | The same, each character mapped by `f` |

| Method | Result |
| --- | --- |
| `g.width`, `g.height`, `g.cells` | The fields: the size, and the cells row by row, `(x, y)` at `cells[y * width + x]` |
| `g.in_bounds(p: (int, int)) -> bool` | Whether `p` is a position of the grid |
| `g.at(p) -> Option<T>` | The cell at `p`; `None` out of bounds |
| `g.set(p, v: T)` | Sets the cell at `p`. Out of bounds it is a failure, as for a list. Needs a `var` place |
| `g.neighbours4(p) -> [(int, int)]` | The positions next to `p` across an edge, in bounds: up, right, down, left. Of a `p` out of bounds, those of its neighbours that are in bounds |
| `g.neighbours8(p) -> [(int, int)]` | Across an edge or a corner, clockwise from up: up, up-right, right, down-right, down, down-left, left, up-left |
| `g.index(p) -> int`, `g.pos(i: int) -> (int, int)` | A position's index in `cells`, `y * width + x`, and back: node numbers for `bfs_dense` and `dijkstra_dense`. A `p` or an `i` out of bounds is a failure |
| `g.positions() -> [(int, int)]` | Every position, row by row |
| `g.iter() -> ListIter<T>` | An iterator over the cells, row by row (D171, [[MYLA-553]]): `for c in g.iter()`, or a pipeline of [[Language/Standard-library/Iter|std.iter]]; the `i`th cell is at `g.pos(i)`. It is `g.cells.iter()`, holding the grid as it was |
| `g.row(y: int) -> [T]`, `g.column(x: int) -> [T]` | The cells of a row, left to right; of a column, top to bottom. A `y` or an `x` out of bounds is a failure, for both alike ([[MYLA-425]]) |
| `g.map<U>(f: (T) -> U) -> Grid<U>` | The grid of `f` of each cell |
| `g.transposed() -> Grid<T>` | The cell at `(x, y)` moved to `(y, x)`: rows become columns |
| `g.find(v: T) -> Option<(int, int)>` | The first position, row by row, whose cell is `v`. `T: Eq` |
| `g.find_all(v: T) -> [(int, int)]` | Every such position, row by row. `T: Eq` |
| `g.text() -> str` | The grid as text, a line a row, each cell as `{}` formats it, no line break after the last row. `T: Format` |

| `GridError` | Meaning |
| --- | --- |
| `Ragged(row, cells, first)` | Row `row` (from 1) has `cells` cells, the first row `first` |

`GridError` has `message()` and implements `Format`, so `print(e)` shows the message (D168).

`Grid<T>` derives `Eq` and `Hash` ([[MYLA-379]]): `a == b` when the sizes and the cells are equal (`T: Eq`), and a grid of `Hash` cells is a map key, a search's state of a whole grid (`[Grid<char>: int]`).

## Positions

A position is an `(int, int)` tuple `(x, y)`. `x` counts columns from the left, `y` rows from the top, so "up" is `y - 1`, as the text reads. A tuple is a map key and a `Set` element as it is (D163), it is written and taken apart without an import (`(x + 1, y)`, `let (x, y) = p`), and it is the node a search of `std.graph` over the grid wants.

A `#derive(Eq, Hash)` struct `Pos { x, y }` was the other choice. It gives names (`p.x`) and could have methods, but its literal `Pos { x: 1, y: 2 }` needs a `from std.grid import Pos` (D170 covers types, not literals), and it isn't faster: a breadth-first search over a 1000×1000 grid keyed by each took 461 to 477 ms with tuples and 465 to 504 ms with the struct.

## Reading text

`parse` splits `text` at `"\n"`; a `"\r"` before one is dropped, and a line break at the end of the text makes no row of its own. A row has a cell for each character, not each byte, so `'·'` or `'█'` is one cell. Every row must have as many cells as the first, an empty line too; the empty text is the grid of no cells. `parse_with` maps each character as it reads it: `(c) => c - '0'` for a grid of digits, `(c) => c == '#'` for a `Grid<bool>` of walls.

`text` is `parse`'s inverse for a `Grid<char>`. A grid of another type prints by `map` first: `g.map((wall) => if wall { '#' } else { '.' }).text()`.

## Limits

- `print(g)` and `f"{g}"` aren't possible: a `Format` impl on the generic `Grid<T>` doesn't link natively ([[MYLA-367]]); write `print(g.text())`.
- `for c in g` isn't possible: a grid isn't an iterator itself (D171), and the checker's message says to write `g.iter()` for the cells; `for p in g.positions()` visits the positions.
