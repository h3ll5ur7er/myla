import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  icon: string;
  title: string;
  body: string;
  tone: 'xp' | 'level' | 'achievement' | 'info' | 'error';
}

// Short notices in a corner: experience gained, a new level, an achievement.
@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private next = 1;

  show(t: Omit<Toast, 'id'>, ms = 4500): void {
    const id = this.next++;
    this.toasts.update((list) => [...list.slice(-3), { ...t, id }]);
    setTimeout(() => this.dismiss(id), ms);
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }
}
