// Applies the chosen theme before the first paint, to avoid a flash
try {
  const t = localStorage.getItem('tema')
  if (t === 'oscuro') document.documentElement.dataset.theme = 'dark'
  if (t === 'claro') document.documentElement.dataset.theme = 'light'
} catch {}
