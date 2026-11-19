/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./apps/**/*.py",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          900: "#312e81",
        },
        // Stitch / Storefront Design System Tokens
        primary: {
          DEFAULT: "#00685d",
          container: "#008376",
          fixed: "#8ff4e3",
          "fixed-dim": "#72d8c8",
        },
        "on-primary": {
          DEFAULT: "#ffffff",
          container: "#f4fffb",
          fixed: "#00201c",
          "fixed-variant": "#005047",
        },
        secondary: {
          DEFAULT: "#565e74",
          container: "#dae2fd",
          fixed: "#dae2fd",
          "fixed-dim": "#bec6e0",
        },
        "on-secondary": {
          DEFAULT: "#ffffff",
          container: "#5c647a",
          fixed: "#131b2e",
          "fixed-variant": "#3f465c",
        },
        tertiary: {
          DEFAULT: "#006b2e",
          container: "#00873c",
          fixed: "#66ff8e",
          "fixed-dim": "#3de273",
        },
        "on-tertiary": {
          DEFAULT: "#ffffff",
          container: "#f7fff3",
          fixed: "#002109",
          "fixed-variant": "#005322",
        },
        surface: {
          DEFAULT: "#f8f9ff",
          bright: "#f8f9ff",
          dim: "#cbdbf5",
          container: {
            lowest: "#ffffff",
            low: "#eff4ff",
            DEFAULT: "#e5eeff",
            high: "#dce9ff",
            highest: "#d3e4fe",
          },
        },
        "on-surface": {
          DEFAULT: "#0b1c30",
          variant: "#3d4946",
        },
        outline: {
          DEFAULT: "#6d7a77",
          variant: "#bdc9c5",
        },
        error: {
          DEFAULT: "#ba1a1a",
          container: "#ffdad6",
        },
        "on-error": {
          DEFAULT: "#ffffff",
          container: "#93000a",
        },
        "inverse-surface": {
          DEFAULT: "#213145",
        },
        "inverse-primary": {
          DEFAULT: "#72d8c8",
        },
        "on-inverse-surface": {
          DEFAULT: "#eaf1ff",
        },
      },
      fontFamily: {
        headline: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        body: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        price: ['"Space Grotesk"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        badge: ['"Space Grotesk"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
