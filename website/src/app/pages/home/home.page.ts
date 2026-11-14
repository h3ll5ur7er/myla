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
  readonly site = resource({ loader: () => this.content.site() });
  readonly hero = splitOutput(hero);
  readonly exercises = computed(() => this.site.value()?.chapters.reduce((n, c) => n + c.exercises, 0) ?? 0);
  readonly levels = LEVELS.filter((l) => [1, 4, 7, 10, 13].includes(l.n));

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
      icon: '🛡️',
      title: 'Checked before it runs',
      body: 'Static types, explicit sizes, no implicit conversions. The interpreter and the native backends only run what the checker accepted, and must agree on every byte they print.',
      code: 'let n: int64 = 5000000000\nlet small = n as int32   // say so',
      link: '/docs/types',
    },
    {
      icon: '📦',
      title: 'Values, not references',
      body: 'Assignment copies. Lists and maps are reference-counted and copy-on-write, so copies are cheap and spooky action at a distance is gone.',
      code: 'var a = [1, 2, 3]\nlet b = a\na.push(4)        // b is still [1, 2, 3]',
      link: '/docs',
    },
    {
      icon: '🧪',
      title: 'Tests live next to the code',
      body: "#test cases above a function are checked by `myla test`, in the interpreter and natively. The standard library's examples on this site are its tests.",
      code: '#test(3, 4)[7]\n#test(-1, 1)[0]\nfun add(a: int, b: int) -> int {\n    return a + b\n}',
      link: '/docs/attributes-and-testing',
    },
    {
      icon: '🔁',
      title: 'It compiles itself',
      body: "The compiler, the interpreter and the language server are written in Myla. The bootstrap reaches a byte-identical fixed point: Myla builds Myla builds Myla.",
      code: '$ scripts/bootstrap.sh\nstage 2 == stage 3   ✓ fixed point',
      link: '/quickstart',
    },
    {
      icon: '🎯',
      title: 'Three targets, no libc',
      body: 'Static x86-64 and aarch64 Linux binaries without libc, and WebAssembly for WASI. The toolchain on this very page is Myla compiled to wasm.',
      code: '$ myla build app.my --target aarch64-linux\n$ myla build app.my --target wasm32-wasi',
      link: '/docs/targets',
    },
    {
      icon: '🔋',
      title: 'Batteries included',
      body: 'JSON, TOML, YAML, regexes, HTTP with a router, compression, archives, big integers, vectors and quaternions: 60 modules, documented down to each method.',
      code: 'import std.json as json\nlet text = json.encode(user)',
      link: '/reference',
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
