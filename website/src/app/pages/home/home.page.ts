import { ChangeDetectionStrategy, Component, computed, inject, resource, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EditorComponent } from '../../editor/editor.component';
import { StarfieldComponent } from '../../shell/starfield.component';
import { highlight } from '../../editor/highlight';
import { splitOutput } from '../../core/sample';
import { ContentService } from '../../core/content.service';
import { LEVELS } from '../../core/gamification';
import hero from './samples/hero.my';
import errors from './samples/errors.my';
import traits from './samples/traits.my';
import actors from './samples/actors.my';
import linalg from './samples/linalg.my';

interface Feature {
  icon: string;
  title: string;
  body: string;
  code: string;
  link: string;
}

@Component({
  selector: 'app-home',
  imports: [RouterLink, EditorComponent, StarfieldComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './home.page.html',
  styleUrl: './home.page.scss',
})
export class HomePage {
  private readonly content = inject(ContentService);
  readonly site = resource({ loader: () => this.content.site().catch(() => null) });
  readonly hero = splitOutput(hero);
  readonly exercises = computed(() => this.site.value()?.chapters.reduce((n, c) => n + c.exercises, 0) ?? 0);
  readonly levels = LEVELS.filter((l) => [1, 5, 11, 16, 20].includes(l.n));

  readonly tastes = [
    { id: 'errors', label: 'Errors as values', file: 'digits.my', ...splitOutput(errors), blurb: 'No exceptions: Result, Option and the ? operator, checked before anything runs.' },
    { id: 'traits', label: 'Traits & generics', file: 'heroes.my', ...splitOutput(traits), blurb: 'Traits with bounds, generics compiled for each type they are used with. Power level: over 9000.' },
    { id: 'actors', label: 'Actors & async', file: 'counter.my', ...splitOutput(actors), blurb: "Concurrency in the style of Swift: an actor's methods run one at a time, child tasks in parallel." },
    { id: 'linalg', label: 'Vectors & matrices', file: 'space.my', ...splitOutput(linalg), blurb: 'Operators between types by trait: pos += vel * dt reads as it should. Column-major, right-handed.' },
  ];
  readonly tab = signal(this.tastes[0].id);
  readonly taste = computed(() => this.tastes.find((t) => t.id === this.tab())!);

  readonly features: Feature[] = [
    {
      icon: '📦',
      title: 'Every value is a value',
      body: 'No references, no borrow checker, no shared mutable state. Assignment copies, and copy-on-write keeps the copies cheap: memory safety without lifetimes.',
      code: 'var a = [1, 2, 3]\nlet b = a\na.push(4)        // b is still [1, 2, 3]',
      link: '/docs/collections-and-strings',
    },
    {
      icon: '🧵',
      title: 'Concurrency without data races',
      body: "Actors and structured tasks, in the style of Swift. Values cross between tasks as copies and an actor's methods run one at a time, so no two tasks ever change the same data.",
      code: 'async let a = fetch(1)\nasync let b = fetch(2)\nprint(await a + await b)',
      link: '/docs/concurrency',
    },
    {
      icon: '🔋',
      title: 'A standard library that goes deep',
      body: 'JSON, TOML, YAML and XML; regexes; an HTTP client and server with a router; TCP and UDP; compression and archives; graphs, heaps and B-trees; big integers, vectors and quaternions. 60 modules, documented down to each method.',
      code: 'import std.regex as regex\nlet re = regex.compile("[0-9]+")?\nlet all = re.find_all(text)',
      link: '/reference',
    },
    {
      icon: '🧪',
      title: 'Examples are tests',
      body: "#test cases above a function are run by myla test, in the interpreter and natively. The standard library's examples on this site are its tests.",
      code: '#test(3, 4)[7]\n#test(-1, 1)[0]\nfun add(a: int, b: int) -> int {\n    return a + b\n}',
      link: '/docs/attributes-and-testing',
    },
    {
      icon: '🛡️',
      title: 'Checked before it runs',
      body: 'Static types and explicit sizes. The interpreter and the native backends only run what the checker accepted, and must agree on every byte they print.',
      code: 'let n: int64 = 5000000000\nlet small = n as int32   // say so',
      link: '/docs/types',
    },
    {
      icon: '🔁',
      title: 'Written in Myla',
      body: 'The compiler, the interpreter and the language server are Myla programs, and the bootstrap reaches a byte-identical fixed point. Every change compiles the compiler: the toughest test the language gets.',
      code: '$ scripts/bootstrap.sh\nstage 2 == stage 3   ✓ fixed point',
      link: '/quickstart',
    },
  ];

  readonly pipeline = [
    { step: 'lexer', what: 'tokens' },
    { step: 'parser', what: 'syntax tree' },
    { step: 'checker', what: 'types, every program' },
    { step: 'interpreter', what: 'myla run, myla test, this page' },
    { step: 'IR', what: 'lowered, optimised' },
    { step: 'x86-64 · aarch64 · wasm32', what: 'myla build' },
  ];

  hl(code: string): string {
    return highlight(code);
  }
}
