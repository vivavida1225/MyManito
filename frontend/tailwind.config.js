/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["TmoneyRoundWind", "sans-serif"],
      },
    },
  },
  plugins: [],
};
