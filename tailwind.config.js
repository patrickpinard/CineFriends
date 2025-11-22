/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js"
  ],
  theme: {
    extend: {
        fontFamily: {
            sans: ['Inter', 'system-ui', 'sans-serif'],
        },
        colors: {
            primary: {
                50: '#ecfdf5',
                100: '#d1fae5',
                200: '#a7f3d0',
                300: '#6ee7b7',
                400: '#34d399',
                500: '#22c55e',
                600: '#16a34a',
                700: '#15803d',
                800: '#166534',
                900: '#14532d',
            },
            teal: {
                500: '#14b8a6',
                600: '#0d9488',
            },
            slate: {
                950: '#020817',
            },
        },
        boxShadow: {
            soft: '0 12px 40px -20px rgba(14, 165, 233, 0.25)',
            card: '0 18px 60px -40px rgba(15, 23, 42, 0.65)',
        },
        borderRadius: {
            xl: '1rem',
            '2xl': '1.5rem',
        },
    }
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
    // line-clamp is now included in core by default in v3.3+, but we can leave it out or check version.
    // The CDN url had ?plugins=forms,typography,aspect-ratio,line-clamp
  ],
}
