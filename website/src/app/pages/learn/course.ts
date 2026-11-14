import { Course } from '../../core/content.types';
import { chapterSolved, chapterUnlocked, exerciseUnlocked, key, Progress } from '../../core/gamification';

// Where to go on: the first unsolved exercise that is open, else none.
export function nextExercise(course: Course, p: Progress): { chapter: string; exercise: string } | null {
  for (let ci = 0; ci < course.chapters.length; ci++) {
    const ch = course.chapters[ci];
    for (let ei = 0; ei < ch.exercises.length; ei++) {
      const ex = ch.exercises[ei];
      if (!p.solved[key(ch.id, ex.id)] && exerciseUnlocked(p, course, ci, ei)) return { chapter: ch.id, exercise: ex.id };
    }
  }
  return null;
}

export interface ChapterView {
  index: number;
  id: string;
  title: string;
  emoji: string;
  tagline: string;
  solved: number;
  total: number;
  unlocked: boolean;
  done: boolean;
  xp: number;
}

export function chapterViews(course: Course, p: Progress): ChapterView[] {
  return course.chapters.map((ch, i) => {
    const solved = chapterSolved(p, ch);
    return {
      index: i,
      id: ch.id,
      title: ch.title,
      emoji: ch.emoji,
      tagline: ch.tagline,
      solved,
      total: ch.exercises.length,
      unlocked: chapterUnlocked(p, course, i),
      done: ch.exercises.length > 0 && solved === ch.exercises.length,
      xp: ch.exercises.reduce((s, e) => s + e.xp, 0),
    };
  });
}
