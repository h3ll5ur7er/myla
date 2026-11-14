// The site's pop culture, in one place so it stays light (MYLA-630).

export const LOADING = [
  'Calculating the Ultimate Answer…',
  'Reversing the polarity of the neutron flow…',
  'Gathering chakra…',
  'Charging the infinite improbability drive…',
  'Optimising middle-out compression…',
  'Setting sail for the Grand Line…',
  'Assembling the Avengers…',
  'Dialing the gate… chevron one encoded…',
  'Brewing a Polyjuice Potion…',
  'Meditating at Kaer Morhen…',
  'Hacking the ctOS…',
  'Punching trees for wood…',
  'Engaging the warp drive…',
  'Following the white rabbit…',
  'Charging the flux capacitor to 1.21 gigawatts…',
  'Waiting for the eagles…',
  'Lighting the Bat-Signal…',
];

export function loadingLine(): string {
  return LOADING[Math.floor(Math.random() * LOADING.length)];
}

export const NOT_FOUND = [
  { quote: 'The page you are looking for has been demolished to make way for a hyperspace bypass.', who: "The Hitchhiker's Guide to the Galaxy" },
  { quote: "This isn't the page you're looking for. Neither is it the One Piece, sadly.", who: 'One Piece, sort of' },
  { quote: 'I am inevitable. This page, apparently, was not.', who: 'Marvel' },
  { quote: 'It works on my machine. — The page, probably', who: 'Silicon Valley' },
  { quote: "Search your feelings. You know this page doesn't exist.", who: 'Star Wars' },
  { quote: 'This page has been Obliviated. It remembers nothing, and neither does the server.', who: 'Harry Potter' },
  { quote: "Wind's howling. And this page is gone.", who: 'The Witcher' },
  { quote: 'Wasted. Respawning at the nearest hospital, which is the home page.', who: 'GTA' },
  { quote: 'You fell into the void. Your items are gone too.', who: 'Minecraft' },
  { quote: "The address doesn't lock. Chevron seven will not engage.", who: 'Stargate SG-1' },
  { quote: "Where we're going, we don't need pages.", who: 'Back to the Future' },
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
  'Mischief managed.',
  'Live long and prosper. And compile.',
  'May the source be with you.',
  "Wind's howling. Tests are passing.",
  'To infinity and beyond! (Bounded by int64.)',
  "It's not who I am underneath, but what I return, that defines me.",
  'Hakuna matata: no undefined behaviour.',
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
  'Mischief managed!',
  'Mission passed! Respect +.',
  'Make it so. And so it was.',
  'Chevron seven locked!',
  'Diamonds!',
  'Toss a coin to your coder.',
  "You're a programmer, Harry.",
  'The Force is strong with this one.',
  "Nobody's ever done that before. Except Geralt, probably.",
  'Hack the planet!',
];

export const FAILED = [
  "I've got a bad feeling about this.",
  'Have you tried turning it off and on again?',
  'Not even a Babel fish could make the tests agree.',
  'Close. Like, Thanos-snapped-half-of-it close.',
  "Don't panic. Read the output, then try again.",
  'The Grand Line is rough. Adjust your course.',
  'Wasted.',
  'Hmm. Medium-rare. The tests, not you.',
  "It's a trap!",
  'Ten points from Gryffindor.',
  'Creeper? Aw man.',
  "Damn it, Jim, I'm a compiler, not a mind reader.",
  'Not this time, Batman.',
  'Even Geralt gets it wrong the first time. Usually on purpose, for the plot.',
];

// A program that ran out of time.
export const TIMEOUT = [
  'Time is an illusion; lunchtime doubly so.',
  'Wasted. A loop that never ends?',
  'Stuck in a time loop. Groundhog Day, again.',
  "Still spinning, like a Witcher's sword at a drowner.",
  "It's been 84 years… (ten seconds, actually).",
];

export function pick<T>(list: T[]): T {
  return list[Math.floor(Math.random() * list.length)];
}
