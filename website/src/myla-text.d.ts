// .my files imported as their text (angular.json's loader), so the site's
// samples are real Myla files the tests run (MYLA-630).
declare module '*.my' {
  const text: string;
  export default text;
}
