import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        // 文字三级的第三级 + 装饰级 + 输入面（VR-GOAL-021，语义见 index.css）。
        // ⚠️ Tailwind 对**未注册**的类名静默无效——`text-subtle` 若漏在这里注册，
        // 元素不会报错、只会继承父级颜色，很可能"看着正常"而永远没人发现。
        // `test_color_token_discipline.py` 里有一条专门比对这里和 .tsx 的实际用法。
        subtle: "hsl(var(--subtle-foreground))",
        faint: "hsl(var(--faint))",
        "input-surface": "hsl(var(--input-surface))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        success: "hsl(var(--success))",
        danger: "hsl(var(--danger))",
        warning: "hsl(var(--warning))",
        info: "hsl(var(--info))",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 4px)", sm: "calc(var(--radius) - 8px)" },
      boxShadow: {
        glass: "0 12px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06)",
        glow: "0 0 0 1px hsl(var(--primary) / .25), 0 0 24px hsl(var(--primary) / .18)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
} satisfies Config;
