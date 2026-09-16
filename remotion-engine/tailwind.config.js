/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        chronos: {
          cyan: "#00FFFF",
          gold: "#FFD700",
          dark: "#050505",
        },
      },
    },
  },
  plugins: [],
};
