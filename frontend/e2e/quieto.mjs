// Espera a que la página termine de pedir datos. No sirve 'networkidle' de
// Playwright: el canal de cambios (/api/cambios, Server-Sent Events) deja una
// conexión abierta todo el tiempo, a propósito.
export function vigilarRed(p) {
  const pendientes = new Set()
  const fuera = (q) => q.url().includes('/api/cambios')
  p.on('request', (q) => { if (!fuera(q)) pendientes.add(q) })
  p.on('requestfinished', (q) => pendientes.delete(q))
  p.on('requestfailed', (q) => pendientes.delete(q))
  // Sin peticiones pendientes durante `calma` ms (o hasta `maximo` ms)
  return async function quieto({ calma = 500, maximo = 15000 } = {}) {
    const fin = Date.now() + maximo
    let desde = Date.now()
    while (Date.now() < fin) {
      if (pendientes.size) desde = Date.now()
      else if (Date.now() - desde >= calma) return
      await p.waitForTimeout(50)
    }
  }
}
