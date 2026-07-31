/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: { '2xl': '1280px' },
    },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        success: {
          DEFAULT: 'hsl(var(--success))',
          foreground: 'hsl(var(--success-foreground))',
        },
        warning: {
          DEFAULT: 'hsl(var(--warning))',
          foreground: 'hsl(var(--warning-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        // Score bands. Status colours, always paired with a visible label.
        band: {
          poor: 'var(--band-poor)',
          fair: 'var(--band-fair)',
          good: 'var(--band-good)',
          excellent: 'var(--band-excellent)',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontFamily: {
        // The authenticated product is the larger surface, so it is the default
        // that Tailwind's preflight puts on <html>. The marketing tree opts into
        // `font-landing` explicitly at its root - keeping the two as separate
        // families means neither can inherit the other's font by accident.
        sans: ['var(--font-app)'],
        app: ['var(--font-app)'],
        landing: ['var(--font-landing)'],
        'landing-body': ['var(--font-landing-body)'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        // Two identical copies of the track sit side by side, so translating
        // exactly -50% lands the second copy where the first began - the loop
        // has no visible seam and never needs to reset.
        marquee: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' },
        },
        // Slow drift for the hero's gradient blobs. Transform and opacity only:
        // both are compositor properties, so an animation that runs forever
        // behind the hero costs no layout or paint work.
        'blob-drift-a': {
          '0%, 100%': { transform: 'translate3d(0, 0, 0) scale(1)', opacity: '0.55' },
          '50%': { transform: 'translate3d(6%, -5%, 0) scale(1.15)', opacity: '0.75' },
        },
        'blob-drift-b': {
          '0%, 100%': { transform: 'translate3d(0, 0, 0) scale(1.08)', opacity: '0.5' },
          '50%': { transform: 'translate3d(-7%, 6%, 0) scale(0.92)', opacity: '0.7' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'fade-in': 'fade-in 0.25s ease-out',
        marquee: 'marquee 38s linear infinite',
        'blob-drift-a': 'blob-drift-a 19s ease-in-out infinite',
        'blob-drift-b': 'blob-drift-b 24s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
