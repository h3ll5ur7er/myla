// The site's pop culture, in one place so it stays light (MYLA-630).

export const LOADING = [
  'Calculating the Ultimate Answer…',
  'Reversing the polarity of the neutron flow…',
  'Gathering chakra…',
  'Charging the infinite improbability drive…',
  'Optimising middle-out compression…',
  'Setting sail for the Grand Line…',
  'Assembling the Avengers…',
];

export function loadingLine(): string {
  return LOADING[Math.floor(Math.random() * LOADING.length)];
}

export const NOT_FOUND = [
  { quote: 'The page you are looking for has been demolished to make way for a hyperspace bypass.', who: "The Hitchhiker's Guide to the Galaxy" },
  { quote: "This isn't the page you're looking for. Neither is it the One Piece, sadly.", who: 'One Piece, sort of' },
  { quote: 'I am inevitable. This page, apparently, was not.', who: 'Marvel' },
  { quote: 'It works on my machine. — The page, probably', who: 'Silicon Valley' },
];

// A footer line, changing with the day.
export const FOOTER = [
  "Don't panic. Bring a towel.",
  'Believe it! Dattebayo.',
  "I'm gonna be King of the Programmers!",
  'Compiles itself. Like Ultron, but friendly.',
  'Tip-to-tip efficiency, middle-out.',
  'So long, and thanks for all the fish.',
  'With great type systems comes great responsibility.',
];

export function footerLine(now = new Date()): string {
  const day = Math.floor(now.getTime() / 86_400_000);
  return FOOTER[day % FOOTER.length];
}

export const SOLVED = [
  'Believe it! Dattebayo!',
  'Excelsior!',
  "That's one small step for a program, one giant leap for your XP.",
  'The tests pass. Gilfoyle grudgingly approves.',
  'Gum-Gum… Pistol! Straight through the bug.',
  "I am inevitable. And so, apparently, are you.",
  'Middle-out. Tip-to-tip efficiency.',
  'Share and enjoy!',
];

export const FAILED = [
  "I've got a bad feeling about this.",
  'Have you tried turning it off and on again?',
  'Not even a Babel fish could make the tests agree.',
  'Close. Like, Thanos-snapped-half-of-it close.',
  "Don't panic. Read the output, then try again.",
  'The Grand Line is rough. Adjust your course.',
];

export function pick<T>(list: T[]): T {
  return list[Math.floor(Math.random() * list.length)];
}
