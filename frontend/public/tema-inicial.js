// Pone el tema y la paleta antes de la primera pintura, para que no parpadee
try {
  const t = localStorage.getItem('tema')
  if (t === 'oscuro') document.documentElement.dataset.theme = 'dark'
  if (t === 'claro') document.documentElement.dataset.theme = 'light'
  document.documentElement.dataset.paleta = localStorage.getItem('paleta') || 'operacion'
} catch {}
