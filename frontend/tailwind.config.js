/** @type {import('tailwindcss').Config} */
// CareerNova AI design tokens. Every page uses these names, so the palette lives here only:
//   brand  — AI indigo (#635BDB = brand-600, 5.2:1 on white, safe for text and buttons)
//   navy   — hero sections and the sidebar (#101B36 = navy-900)
//   mint   — progress and success highlights (#EAF7F3 = mint-50)
//   slate  — re-tuned neutrals: slate-50 = page background #F5F6FA, slate-500 = secondary text
//            #697386 (4.8:1 on white), slate-900 = primary text #172033
//   violet — secondary AI accent (Tailwind default violet scale)
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#F1F0FD",
          100: "#E4E2FB",
          200: "#CBC8F6",
          300: "#AEA9F0",
          400: "#918AE8",
          500: "#7770E1",
          600: "#635BDB",
          700: "#4F47C4",
          800: "#3F389F",
          900: "#2F2A78",
        },
        navy: {
          600: "#2C3E6E",
          700: "#22335F",
          800: "#18264A",
          900: "#101B36",
          950: "#0A1226",
        },
        mint: {
          50: "#EAF7F3",
          100: "#D3EFE6",
          200: "#A9DECD",
          300: "#76C8AE",
          400: "#45B08F",
          500: "#2A9776",
          600: "#1F7C61",
          700: "#18624D",
          800: "#134E3E",
          900: "#0F3D31",
        },
        slate: {
          50: "#F5F6FA",
          100: "#EDF0F5",
          200: "#E1E5EC",
          300: "#CBD1DB",
          400: "#98A1B0",
          500: "#697386",
          600: "#515B6E",
          700: "#3B4559",
          800: "#262F44",
          900: "#172033",
          950: "#0D1424",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        display: ["\"Plus Jakarta Sans\"", "Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16, 27, 54, 0.04), 0 1px 3px rgba(16, 27, 54, 0.06)",
        "card-hover": "0 4px 6px -2px rgba(16, 27, 54, 0.05), 0 12px 24px -6px rgba(16, 27, 54, 0.10)",
        elevated: "0 20px 40px -12px rgba(16, 27, 54, 0.25)",
        glow: "0 0 0 1px rgba(99, 91, 219, 0.08), 0 8px 24px -8px rgba(99, 91, 219, 0.45)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "fade-in-up": { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        "scale-in": { from: { opacity: "0", transform: "scale(0.97)" }, to: { opacity: "1", transform: "scale(1)" } },
        "slide-in-left": { from: { transform: "translateX(-100%)" }, to: { transform: "translateX(0)" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        float: { "0%, 100%": { transform: "translate(0, 0)" }, "50%": { transform: "translate(12px, -10px)" } },
        "grow-x": { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out both",
        "fade-in-up": "fade-in-up 320ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "scale-in": "scale-in 180ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-in-left": "slide-in-left 240ms cubic-bezier(0.22, 1, 0.36, 1) both",
        shimmer: "shimmer 1.4s infinite",
        float: "float 14s ease-in-out infinite",
        "grow-x": "grow-x 700ms cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [],
};
