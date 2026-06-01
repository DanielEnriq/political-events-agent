/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0a",
        surface: "#141414",
        border: "#2a2a2a",
        muted: "#a8a29e",
        text: "#f5f0e8",
        accent: "#e8d5b0",
      },
    },
  },
  plugins: [],
};
