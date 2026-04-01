module.exports = {
  content: [
    "./js/**/*.js",
    "../lib/nexus_ui_web/**/*.*ex",
    "../lib/nexus_ui_web/**/*.heex",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
  safelist: [
    // Dynamic color classes used in LiveViews
    { pattern: /bg-(green|red|yellow|blue|gray|orange|purple)-(50|100|200|400|600|700|800|950)/ },
    { pattern: /text-(green|red|yellow|blue|gray|orange|purple)-(400|600|700|800)/ },
    { pattern: /border-(green|red|yellow|blue|gray)-(200|300|400)/ },
    { pattern: /ring-(blue|green|yellow)-(400|500)/ },
  ],
}
