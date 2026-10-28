/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#050816',
          900: '#0a0f1f',
          800: '#111729',
          700: '#1b2236',
          600: '#283048',
        },
        // Brand accent. `cyan-*` utilities are remapped to a calm enterprise blue so the
        // whole app shares one primary colour.
        cyan: {
          50: '#eff5ff',
          100: '#dbe8fe',
          200: '#bfd5fe',
          300: '#93b8fd',
          400: '#6094fa',
          500: '#3b72f6',
          600: '#2557eb',
          700: '#1d45d8',
          800: '#1e3aaf',
          900: '#1e348a',
        },
        brand: {
          cyan: '#3b72f6',
          violet: '#7c3aed',
        },
      },
      fontFamily: {
        // One typeface throughout; headings get tighter tracking in index.css.
        serif: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.05)',
        pop: '0 12px 32px -12px rgba(16,24,40,0.18), 0 4px 8px -4px rgba(16,24,40,0.06)',
        glow: '0 0 0 1px rgba(59,114,246,0.25), 0 8px 24px rgba(59,114,246,0.18)',
      },
      keyframes: {
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        fadeIn: {
          '0%': { opacity: 0, transform: 'translateY(4px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        scan: 'scan 2.2s linear infinite',
        fadeIn: 'fadeIn .3s ease-out both',
      },
    },
  },
  plugins: [],
}
