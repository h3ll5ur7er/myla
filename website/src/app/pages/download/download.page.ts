import { ChangeDetectionStrategy, Component, computed, resource } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { REPO } from '../../core/links';

interface Manifest {
  commit: string;
  date: string;
  files: { name: string; platform: string; size: number; sha256: string }[];
}

// Download: the tools of the latest master build, which CI publishes with
// the site (downloads/manifest.json, MYLA-635); building from source always.
@Component({
  selector: 'app-download',
  imports: [RouterLink, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './download.page.html',
  styleUrl: './download.page.scss',
})
export class DownloadPage {
  readonly repo = REPO;
  readonly manifest = resource({
    loader: async () => {
      try {
        const r = await fetch('downloads/manifest.json');
        return r.ok ? ((await r.json()) as Manifest) : null;
      } catch {
        return null;
      }
    },
  });
  readonly files = computed(() => this.manifest.value()?.files ?? []);
  readonly platforms = [
    { id: 'x86_64-linux', icon: '🐧', title: 'Linux x86-64', body: 'A static binary, no libc: myla and myla-lsp.' },
    { id: 'aarch64-linux', icon: '🍓', title: 'Linux aarch64', body: 'ARM servers, a Raspberry Pi 4 or 5 with a 64-bit OS.' },
    { id: 'vscode', icon: '🧩', title: 'VS Code extension', body: 'Highlighting, diagnostics, hovers, go-to-definition and a debugger.' },
  ];

  file(platform: string) {
    return this.files().find((f) => f.platform === platform) ?? null;
  }

  mb(bytes: number): number {
    return bytes / 1_048_576;
  }
}
