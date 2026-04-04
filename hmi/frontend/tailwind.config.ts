import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#05090d",
        panel: "#08131a",
        panel2: "#0b1a23",
        line: "#113341",
        neon: "#29f0ff",
        accent: "#19d398",
        warn: "#ffbf3a",
        danger: "#ff5f70",
        text: "#d5e9f2",
        mute: "#7fa6b8"
      },
      boxShadow: {
        panel: "0 0 0 1px rgba(41,240,255,0.12), inset 0 0 40px rgba(0,0,0,0.24)",
        glow: "0 0 24px rgba(41,240,255,0.25)"
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(41,240,255,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(41,240,255,0.07) 1px, transparent 1px)"
      }
    }
  },
  plugins: []
} satisfies Config;
