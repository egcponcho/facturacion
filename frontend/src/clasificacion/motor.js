import { t as tr } from '../i18n/index.js'
/* Motor de clasificación arancelaria (SAC, Centroamérica y Panamá).

Viene del clasificador SAC: reglas del Sistema Armonizado 2022 para ropa,
calzado, bolsos y accesorios, detección desde el texto del estilo, lectura de
la composición, verificación del código frente a los datos y elección del
inciso nacional de cada país. Es lógica pura: no toca la pantalla ni guarda
nada; la ficha técnica y lo aprendido se guardan en el servidor.

Los textos oficiales del SAC (DESC, CAPITULOS) y la descripción aduanera que
se arma para aduana quedan en español; todo lo demás está en inglés. */
const norm = s => (s == null ? '' : String(s)).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const digits = s => (s == null ? '' : String(s)).replace(/\D/g, '');
function fmtCode(c){
  const d = digits(c);
  if (d.length <= 4) return d;
  let o = d.slice(0,4) + '.' + d.slice(4,6);
  for (let i = 6; i < d.length; i += 2) o += '.' + d.slice(i, i+2);
  return o;
}

const CAPITULOS = {
'48':'Papel y cartón','49':'Productos editoriales e impresos','58':'Tejidos especiales, etiquetas y bordados','44':'Madera y sus manufacturas',
  '28':'Productos químicos inorgánicos','38':'Productos diversos de las industrias químicas','40':'Caucho y sus manufacturas','70':'Vidrio y sus manufacturas','71':'Costume jewelry','83':'Manufacturas diversas de metal común','85':'Máquinas y aparatos eléctricos','91':'Relojería',
  '34':'Jabones, ceras y preparaciones para lustrar','39':'Plástico y sus manufacturas','42':'Manufacturas de cuero, artículos de viaje y bolsos',
  '61':'Prendas y complementos de vestir, de punto','62':'Prendas y complementos de vestir, excepto de punto','63':'Other made-up textile articles',
  '64':'Calzado y sus partes','65':'Sombreros y demás tocados','66':'Paraguas, sombrillas y bastones','73':'Manufacturas de hierro o acero',
  '76':'Aluminio y sus manufacturas','90':'Instrumentos de óptica','94':'Artículos de cama y similares','95':'Artículos para deporte','96':'Manufacturas diversas'
};

const DESC = {
  '4202':'Baúles, maletas, bolsos, mochilas, billeteras y continentes similares',
  '420211':'Maletas, trolleys y maletines, superficie exterior de cuero','420212':'Maletas, trolleys y maletines, superficie exterior de plástico o materia textil','420219':'Maletas, trolleys y maletines, superficie exterior de otras materias',
  '420221':'Bolsos de mano, superficie exterior de cuero','420222':'Bolsos de mano, superficie exterior de hojas de plástico o materia textil','420229':'Bolsos de mano, superficie exterior de otras materias',
  '420231':'Billeteras y artículos de bolsillo, de cuero','420232':'Billeteras y artículos de bolsillo, de hojas de plástico o materia textil','420239':'Billeteras y artículos de bolsillo, de otras materias',
  '420291':'Mochilas, bolsos de viaje y deporte, superficie exterior de cuero','420292':'Mochilas, bolsos de viaje y deporte, loncheras y neceseres, superficie exterior de hojas de plástico o materia textil','420299':'Mochilas, bolsos de viaje y deporte, superficie exterior de otras materias',
  '4203':'Prendas y complementos de vestir de cuero','420310':'Prendas de vestir de cuero','420321':'Guantes de cuero diseñados especialmente para deporte','420329':'Demás guantes de cuero','420330':'Cintos y cinturones de cuero',
  '6101':'Chaquetas, anoraks y similares de punto, hombre o niño','610120':'Chaquetas y anoraks de punto, hombre: de algodón','610130':'Chaquetas y anoraks de punto, hombre: de fibras sintéticas o artificiales','610190':'Chaquetas y anoraks de punto, hombre: de las demás materias textiles',
  '6102':'Chaquetas, anoraks y similares de punto, mujer o niña','610210':'Chaquetas y anoraks de punto, mujer: de lana o pelo fino','610220':'Chaquetas y anoraks de punto, mujer: de algodón','610230':'Chaquetas y anoraks de punto, mujer: de fibras sintéticas o artificiales','610290':'Chaquetas y anoraks de punto, mujer: de las demás materias textiles',
  '6103':'Trajes, sacos, pantalones y shorts de punto, hombre o niño','610341':'Pantalones y shorts de punto, hombre: de lana','610342':'Pantalones y shorts de punto, hombre: de algodón','610343':'Pantalones y shorts de punto, hombre: de fibras sintéticas','610349':'Pantalones y shorts de punto, hombre: de las demás materias textiles',
  '6104':'Vestidos, faldas, pantalones y shorts de punto, mujer o niña',
  '610441':'Vestidos de punto: de lana','610442':'Vestidos de punto: de algodón','610443':'Vestidos de punto: de fibras sintéticas','610444':'Vestidos de punto: de fibras artificiales','610449':'Vestidos de punto: de las demás materias textiles',
  '610451':'Faldas de punto: de lana','610452':'Faldas de punto: de algodón','610453':'Faldas de punto: de fibras sintéticas','610459':'Faldas de punto: de las demás materias textiles',
  '610461':'Pantalones y shorts de punto, mujer: de lana','610462':'Pantalones y shorts de punto, mujer: de algodón','610463':'Pantalones y shorts de punto, mujer: de fibras sintéticas','610469':'Pantalones y shorts de punto, mujer: de las demás materias textiles',
  '6105':'Camisas y polos de punto, hombre o niño','610510':'Camisas y polos de punto, hombre: de algodón','610520':'Camisas y polos de punto, hombre: de fibras sintéticas o artificiales','610590':'Camisas y polos de punto, hombre: de las demás materias textiles',
  '6106':'Camisas, blusas y polos de punto, mujer o niña','610610':'Blusas y camisas de punto, mujer: de algodón','610620':'Blusas y camisas de punto, mujer: de fibras sintéticas o artificiales','610690':'Blusas y camisas de punto, mujer: de las demás materias textiles',
  '6107':'Calzoncillos, bóxers y similares de punto, hombre o niño','610711':'Calzoncillos y bóxers de punto: de algodón','610712':'Calzoncillos y bóxers de punto: de fibras sintéticas o artificiales','610719':'Calzoncillos y bóxers de punto: de las demás materias textiles',
  '6108':'Calzones, bragas y similares de punto, mujer o niña','610821':'Calzones de punto: de algodón','610822':'Calzones de punto: de fibras sintéticas o artificiales','610829':'Calzones de punto: de las demás materias textiles',
  '6109':'T-shirts y camisetas de punto','610910':'T-shirts y camisetas de punto: de algodón','610990':'T-shirts y camisetas de punto: de las demás materias textiles',
  '6110':'Suéteres, pullovers, sudaderas y cardiganes de punto','611011':'Suéteres y sudaderas de punto: de lana','611020':'Suéteres y sudaderas de punto: de algodón','611030':'Suéteres y sudaderas de punto: de fibras sintéticas o artificiales','611090':'Suéteres y sudaderas de punto: de las demás materias textiles',
  '6111':'Prendas y complementos de vestir de punto para bebé','611120':'Prendas de punto para bebé: de algodón','611130':'Prendas de punto para bebé: de fibras sintéticas','611190':'Prendas de punto para bebé: de las demás materias textiles',
  '6112':'Conjuntos deportivos, trajes de esquí y trajes de baño, de punto','611211':'Conjuntos deportivos de punto: de algodón','611212':'Conjuntos deportivos de punto: de fibras sintéticas','611219':'Conjuntos deportivos de punto: de las demás materias textiles','611220':'Trajes de esquí de punto',
  '611231':'Trajes de baño de punto, hombre: de fibras sintéticas','611239':'Trajes de baño de punto, hombre: de las demás materias textiles','611241':'Trajes de baño de punto, mujer: de fibras sintéticas','611249':'Trajes de baño de punto, mujer: de las demás materias textiles',
  '611300':'Prendas confeccionadas con tejidos de punto recubiertos o laminados (5903, 5906, 5907)',
  '6115':'Calcetines y demás medias de punto','611594':'Calcetines de punto: de lana','611595':'Calcetines de punto: de algodón','611596':'Calcetines de punto: de fibras sintéticas','611599':'Calcetines de punto: de las demás materias textiles',
  '6116':'Guantes de punto','611610':'Guantes de punto impregnados, recubiertos o revestidos de plástico o caucho','611691':'Guantes de punto: de lana','611692':'Guantes de punto: de algodón','611693':'Guantes de punto: de fibras sintéticas','611699':'Guantes de punto: de las demás materias textiles',
  '611710':'Chales, bufandas, cuellos y artículos similares, de punto','611780':'Demás complementos de vestir de punto (incluye cinturones de punto)',
  '6201':'Chaquetas, anoraks, cortavientos y chalecos acolchados, hombre o niño (tejido plano)','620120':'Chaquetas y anoraks, hombre: de lana','620130':'Chaquetas y anoraks, hombre: de algodón','620140':'Chaquetas y anoraks, hombre: de fibras sintéticas o artificiales','620190':'Chaquetas y anoraks, hombre: de las demás materias textiles',
  '6202':'Chaquetas, anoraks, cortavientos y chalecos acolchados, mujer o niña (tejido plano)','620220':'Chaquetas y anoraks, mujer: de lana','620230':'Chaquetas y anoraks, mujer: de algodón','620240':'Chaquetas y anoraks, mujer: de fibras sintéticas o artificiales','620290':'Chaquetas y anoraks, mujer: de las demás materias textiles',
  '6203':'Trajes, sacos, pantalones y shorts, hombre o niño (tejido plano)','620331':'Sacos tipo traje, hombre: de lana','620332':'Sacos tipo traje, hombre: de algodón','620333':'Sacos tipo traje, hombre: de fibras sintéticas','620339':'Sacos tipo traje, hombre: de las demás materias textiles',
  '620341':'Pantalones, overoles y shorts, hombre: de lana','620342':'Pantalones, overoles y shorts, hombre: de algodón','620343':'Pantalones, overoles y shorts, hombre: de fibras sintéticas','620349':'Pantalones, overoles y shorts, hombre: de las demás materias textiles',
  '6204':'Sacos, vestidos, faldas, pantalones y shorts, mujer o niña (tejido plano)','620431':'Sacos tipo traje, mujer: de lana','620432':'Sacos tipo traje, mujer: de algodón','620433':'Sacos tipo traje, mujer: de fibras sintéticas','620439':'Sacos tipo traje, mujer: de las demás materias textiles',
  '620441':'Vestidos: de lana','620442':'Vestidos: de algodón','620443':'Vestidos: de fibras sintéticas','620444':'Vestidos: de fibras artificiales','620449':'Vestidos: de las demás materias textiles',
  '620451':'Faldas: de lana','620452':'Faldas: de algodón','620453':'Faldas: de fibras sintéticas','620459':'Faldas: de las demás materias textiles',
  '620461':'Pantalones, overoles y shorts, mujer: de lana','620462':'Pantalones, overoles y shorts, mujer: de algodón','620463':'Pantalones, overoles y shorts, mujer: de fibras sintéticas','620469':'Pantalones, overoles y shorts, mujer: de las demás materias textiles',
  '6205':'Camisas de tejido plano, hombre o niño','620520':'Camisas, hombre: de algodón','620530':'Camisas, hombre: de fibras sintéticas o artificiales','620590':'Camisas, hombre: de las demás materias textiles',
  '6206':'Camisas y blusas de tejido plano, mujer o niña','620610':'Blusas y camisas, mujer: de seda','620620':'Blusas y camisas, mujer: de lana','620630':'Blusas y camisas, mujer: de algodón','620640':'Blusas y camisas, mujer: de fibras sintéticas o artificiales','620690':'Blusas y camisas, mujer: de las demás materias textiles',
  '6207':'Calzoncillos y ropa interior de tejido plano, hombre o niño','620711':'Calzoncillos de tejido plano: de algodón','620719':'Calzoncillos de tejido plano: de las demás materias textiles',
  '6208':'Ropa interior y de dormir de tejido plano, mujer o niña','620891':'Ropa interior de tejido plano, mujer: de algodón','620892':'Ropa interior de tejido plano, mujer: de fibras sintéticas o artificiales','620899':'Ropa interior de tejido plano, mujer: de las demás materias textiles',
  '6209':'Prendas y complementos de vestir para bebé (tejido plano)','620920':'Prendas para bebé, tejido plano: de algodón','620930':'Prendas para bebé, tejido plano: de fibras sintéticas','620990':'Prendas para bebé, tejido plano: de las demás materias textiles',
  '621020':'Chaquetas y anoraks de hombre, de tejidos recubiertos o laminados (5903, 5906, 5907)','621030':'Chaquetas y anoraks de mujer, de tejidos recubiertos o laminados (5903, 5906, 5907)','621040':'Demás prendas de hombre, de tejidos recubiertos o laminados (5903, 5906, 5907)','621050':'Demás prendas de mujer, de tejidos recubiertos o laminados (5903, 5906, 5907)',
  '6211':'Conjuntos deportivos, trajes de esquí, trajes de baño y demás prendas (tejido plano)','621111':'Trajes de baño, hombre (tejido plano)','621112':'Trajes de baño, mujer (tejido plano)','621120':'Trajes de esquí (tejido plano)',
  '621132':'Conjuntos deportivos y demás prendas, hombre: de algodón','621133':'Conjuntos deportivos y demás prendas, hombre: de fibras sintéticas o artificiales','621139':'Conjuntos deportivos y demás prendas, hombre: de las demás materias textiles',
  '621142':'Conjuntos deportivos y demás prendas, mujer: de algodón','621143':'Conjuntos deportivos y demás prendas, mujer: de fibras sintéticas o artificiales','621149':'Conjuntos deportivos y demás prendas, mujer: de las demás materias textiles',
  '621210':'Sostenes (brasieres), incluidos los deportivos',
  '6214':'Chales, bufandas y artículos similares, de tejido plano','621410':'Bufandas y chales: de seda','621420':'Bufandas y chales: de lana','621430':'Bufandas y chales: de fibras sintéticas','621440':'Bufandas y chales: de fibras artificiales','621490':'Bufandas y chales: de las demás materias textiles',
  '621600':'Guantes de tejido plano','621710':'Complementos de vestir de tejido plano (incluye cinturones de tela)',
  '6306':'Toldos, tiendas de campaña y artículos de acampar','630622':'Tiendas de campaña: de fibras sintéticas','630629':'Tiendas de campaña: de las demás materias textiles',
  '630790':'Demás artículos textiles confeccionados (incluye cordones para calzado)',
  '650500':'Sombreros, gorras, beanies y demás tocados de punto o de tela','650610':'Cascos de seguridad','650699':'Demás tocados de otras materias',
  '660191':'Paraguas y sombrillas con astil o mango telescópico','660199':'Demás paraguas y sombrillas','660200':'Bastones, bastones asiento y similares',
  '940430':'Sacos de dormir','950699':'Demás artículos para deporte (incluye patinetas)',
  '340510':'Betunes, cremas y preparaciones similares para calzado o cuero','392410':'Vajilla y artículos de cocina o servicio de mesa, de plástico (incluye botellas)','392620':'Prendas y complementos de vestir de plástico (incluye cinturones)',
  '732393':'Artículos de uso doméstico de acero inoxidable (incluye botellas)','761510':'Artículos de uso doméstico de aluminio (incluye botellas)','900410':'Gafas (anteojos) de sol','960390':'Demás cepillos (incluye cepillos para calzado)','961700':'Termos y demás recipientes isotérmicos al vacío',
  '610331':'Sacos y blazers de punto, hombre: de lana','610332':'Sacos y blazers de punto, hombre: de algodón','610333':'Sacos y blazers de punto, hombre: de fibras sintéticas','610339':'Sacos y blazers de punto, hombre: de las demás materias textiles',
  '610431':'Sacos y blazers de punto, mujer: de lana','610432':'Sacos y blazers de punto, mujer: de algodón','610433':'Sacos y blazers de punto, mujer: de fibras sintéticas','610439':'Sacos y blazers de punto, mujer: de las demás materias textiles',
  '610721':'Pijamas y camisones de punto, hombre: de algodón','610722':'Pijamas y camisones de punto, hombre: de fibras sintéticas o artificiales','610729':'Pijamas y camisones de punto, hombre: de las demás materias textiles',
  '610831':'Pijamas y camisones de punto, mujer: de algodón','610832':'Pijamas y camisones de punto, mujer: de fibras sintéticas o artificiales','610839':'Pijamas y camisones de punto, mujer: de las demás materias textiles',
  '6114':'Demás prendas de punto (enterizos, monos, chalecos de seguridad)','611420':'Demás prendas de punto (enterizos, chalecos de seguridad): de algodón','611430':'Demás prendas de punto (enterizos, chalecos de seguridad): de fibras sintéticas o artificiales','611490':'Demás prendas de punto (enterizos, chalecos de seguridad): de las demás materias textiles',
  '620721':'Pijamas de tejido plano, hombre: de algodón','620722':'Pijamas de tejido plano, hombre: de fibras sintéticas o artificiales','620729':'Pijamas de tejido plano, hombre: de las demás materias textiles',
  '620791':'Camisetas interiores y albornoces de tejido plano, hombre: de algodón','620799':'Camisetas interiores y albornoces de tejido plano, hombre: de las demás materias textiles',
  '620821':'Camisones y pijamas de tejido plano, mujer: de algodón','620822':'Camisones y pijamas de tejido plano, mujer: de fibras sintéticas o artificiales','620829':'Camisones y pijamas de tejido plano, mujer: de las demás materias textiles',
  '6213':'Pañuelos y bandanas','621320':'Pañuelos y bandanas: de algodón','621390':'Pañuelos y bandanas: de las demás materias textiles',
  '6301':'Mantas','630120':'Mantas: de lana o pelo fino','630130':'Mantas: de algodón','630140':'Mantas: de fibras sintéticas','630190':'Mantas: de las demás materias textiles',
  '630640':'Colchones neumáticos (inflables) de materia textil','650400':'Sombreros y tocados de paja o de tiras trenzadas',
  '283699':'Demás carbonatos (incluye carbonato de magnesio para escalar)','382499':'Demás preparaciones químicas (mezclas)','392640':'Estatuillas y artículos de adorno de plástico','392690':'Demás manufacturas de plástico',
  '420500':'Demás manufacturas de cuero','711719':'Bisutería de metal común','732690':'Demás manufacturas de hierro o acero',
  '851762':'Aparatos para recibir, convertir y transmitir datos (incluye relojes inteligentes)','910211':'Relojes de pulsera eléctricos, con indicador mecánico (analógicos)','910212':'Relojes de pulsera eléctricos, con indicador optoelectrónico (digitales)','910219':'Demás relojes de pulsera eléctricos (analógico y digital)',
  '940171':'Asientos con armazón de metal, con relleno','940179':'Demás asientos con armazón de metal','940429':'Colchones de otras materias (espuma)','950691':'Artículos para cultura física, gimnasia o atletismo',
  '420100':'Artículos de talabartería para animales: collares, correas, arneses y abrigos para perro','711711':'Gemelos y pasadores de metal común','711790':'Bisutería de otras materias (plástico, madera, vidrio)',
  '491191':'Estampas, imágenes y fotografías impresas (incluye stickers)','490890':'Calcomanías por transferencia','580710':'Etiquetas, escudos y artículos similares, tejidos','581091':'Bordados sin fondo visible o en piezas: de algodón','581092':'Bordados en piezas: de fibras sintéticas o artificiales','581099':'Bordados en piezas: de las demás materias textiles',
  '851310':'Lámparas eléctricas portátiles (linternas y frontales)','950662':'Pelotas y balones inflables','940320':'Demás muebles de metal','940360':'Demás muebles de madera','940370':'Muebles de plástico','961800':'Maniquíes y artículos similares',
  '481910':'Cajas de papel o cartón corrugado','481920':'Cajas y cartonajes plegables de papel o cartón sin corrugar','481940':'Demás sacos y bolsas de papel','392310':'Cajas y artículos similares de plástico','392321':'Sacos y bolsas de polímeros de etileno','392329':'Sacos y bolsas de los demás plásticos',
  '732620':'Manufacturas de alambre de hierro o acero','442110':'Perchas para prendas de vestir, de madera','482110':'Etiquetas impresas de papel o cartón','630590':'Sacos y talegas para envasar, de las demás materias textiles','401699':'Demás manufacturas de caucho vulcanizado',
  '6302':'Ropa de cama, mesa, tocador o cocina (incluye toallas)','630260':'Toallas y ropa de tocador, de tejido de rizo de algodón','630291':'Demás ropa de tocador: de algodón','630293':'Demás ropa de tocador: de fibras sintéticas o artificiales','630299':'Demás ropa de tocador: de las demás materias textiles',
  '940490':'Demás artículos de cama y similares (almohadas, cojines)','610791':'Batas y albornoces de punto, hombre: de algodón','610799':'Batas y albornoces de punto, hombre: de las demás materias textiles','610891':'Batas y albornoces de punto, mujer: de algodón','610892':'Batas y albornoces de punto, mujer: de fibras sintéticas o artificiales','610899':'Batas y albornoces de punto, mujer: de las demás materias textiles',
  '64':'Footwear',
  '6401':'Calzado impermeable de caucho o plástico, sin costuras ni remaches','640110':'Calzado impermeable con puntera metálica de protección','640192':'Calzado impermeable que cubre el tobillo sin cubrir la rodilla','640199':'Demás calzado impermeable',
  '6402':'Demás calzado con suela y corte de caucho o plástico','640212':'Calzado de esquí y snowboard, de caucho o plástico','640219':'Demás calzado de deporte, de caucho o plástico','640220':'Calzado con tiras fijadas a la suela por tetones','640291':'Demás calzado de caucho o plástico que cubre el tobillo','640299':'Demás calzado de caucho o plástico',
  '6403':'Calzado con corte de cuero natural','640312':'Calzado de esquí y snowboard con corte de cuero','640319':'Demás calzado de deporte con corte de cuero','640320':'Calzado con suela de cuero y corte de tiras sobre el empeine que rodean el dedo gordo','640340':'Calzado con corte de cuero y puntera metálica de protección','640351':'Calzado con suela y corte de cuero, que cubre el tobillo','640359':'Demás calzado con suela y corte de cuero','640391':'Calzado con corte de cuero y suela de caucho o plástico, que cubre el tobillo','640399':'Demás calzado con corte de cuero y suela de caucho o plástico',
  '6404':'Calzado con corte de materia textil','640411':'Calzado de deporte; de tenis, baloncesto, gimnasia, entrenamiento y similares (corte textil, suela de caucho o plástico)','640419':'Demás calzado con corte textil y suela de caucho o plástico','640420':'Calzado con corte textil y suela de cuero',
  '6405':'Demás calzado','640510':'Demás calzado con corte de cuero','640520':'Demás calzado con corte textil','640590':'Demás calzado',
  '6406':'Partes de calzado','640610':'Cortes (partes superiores) de calzado','640690':'Demás partes de calzado: plantillas, taloneras, polainas y similares'
};
/* Subpartidas del Sistema Armonizado 2022 para ropa, calzado, bolsos y accesorios (comunes a todo Centroamérica) */
const DESC_EXTRA = {
  '420100':'Artículos de talabartería para animales','420211':'Maletas y maletines, superficie de cuero','420212':'Maletas y maletines, superficie de plástico o textil','420219':'Maletas y maletines, de otras materias',
  '420221':'Bolsos de mano, superficie de cuero','420222':'Bolsos de mano, superficie de hojas de plástico o textil','420229':'Bolsos de mano, de otras materias','420231':'Artículos de bolsillo o de bolso, de cuero','420232':'Artículos de bolsillo o de bolso, de hojas de plástico o textil','420239':'Artículos de bolsillo o de bolso, de otras materias',
  '420291':'Demás continentes (mochilas, bolsos de viaje o deporte), de cuero','420292':'Demás continentes (mochilas, bolsos de viaje o deporte), de hojas de plástico o textil','420299':'Demás continentes, de otras materias',
  '420310':'Prendas de vestir de cuero','420321':'Guantes de cuero para deporte','420329':'Demás guantes de cuero','420330':'Cintos, cinturones y bandoleras de cuero','420340':'Demás complementos de vestir de cuero','420500':'Demás manufacturas de cuero','420600':'Manufacturas de tripa, vejigas o tendones',
  '610120':'Abrigos y chaquetas de punto, hombre: de algodón','610130':'Abrigos y chaquetas de punto, hombre: de fibras sintéticas o artificiales','610190':'Abrigos y chaquetas de punto, hombre: de las demás materias textiles',
  '610210':'Abrigos y chaquetas de punto, mujer: de lana','610220':'Abrigos y chaquetas de punto, mujer: de algodón','610230':'Abrigos y chaquetas de punto, mujer: de fibras sintéticas o artificiales','610290':'Abrigos y chaquetas de punto, mujer: de las demás materias textiles',
  '610310':'Trajes de punto, hombre','610322':'Conjuntos de punto, hombre: de algodón','610323':'Conjuntos de punto, hombre: de fibras sintéticas','610329':'Conjuntos de punto, hombre: de las demás materias textiles',
  '610413':'Trajes sastre de punto, mujer: de fibras sintéticas','610419':'Trajes sastre de punto, mujer: de las demás materias textiles','610422':'Conjuntos de punto, mujer: de algodón','610423':'Conjuntos de punto, mujer: de fibras sintéticas','610429':'Conjuntos de punto, mujer: de las demás materias textiles',
  '610811':'Combinaciones y enaguas de punto: de fibras sintéticas o artificiales','610819':'Combinaciones y enaguas de punto: de las demás materias textiles',
  '611012':'Suéteres de punto: de cabra de Cachemira','611019':'Suéteres de punto: de los demás pelos finos',
  '611510':'Medias de compresión graduada','611521':'Pantimedias de fibras sintéticas, menos de 67 decitex','611522':'Pantimedias de fibras sintéticas, 67 decitex o más','611529':'Pantimedias de las demás materias textiles','611530':'Demás medias de mujer, menos de 67 decitex',
  '611790':'Partes de prendas o complementos de punto',
  '620311':'Trajes de hombre: de lana','620312':'Trajes de hombre: de fibras sintéticas','620319':'Trajes de hombre: de las demás materias textiles','620322':'Conjuntos de hombre: de algodón','620323':'Conjuntos de hombre: de fibras sintéticas','620329':'Conjuntos de hombre: de las demás materias textiles',
  '620411':'Trajes sastre de mujer: de lana','620412':'Trajes sastre de mujer: de algodón','620413':'Trajes sastre de mujer: de fibras sintéticas','620419':'Trajes sastre de mujer: de las demás materias textiles',
  '620421':'Conjuntos de mujer: de lana','620422':'Conjuntos de mujer: de algodón','620423':'Conjuntos de mujer: de fibras sintéticas','620429':'Conjuntos de mujer: de las demás materias textiles',
  '620811':'Combinaciones y enaguas de tejido plano: de fibras sintéticas o artificiales','620819':'Combinaciones y enaguas de tejido plano: de las demás materias textiles',
  '621010':'Prendas de fieltro o tela sin tejer (5602, 5603)','621220':'Fajas y fajas braga','621230':'Fajas sostén (corsés)','621290':'Tirantes, ligas y demás artículos similares',
  '621510':'Corbatas y lazos: de seda','621520':'Corbatas y lazos: de fibras sintéticas o artificiales','621590':'Corbatas y lazos: de las demás materias textiles','621790':'Partes de prendas o complementos de tejido plano',
  '630110':'Mantas eléctricas','630612':'Toldos y lonas: de fibras sintéticas','630619':'Toldos y lonas: de las demás materias textiles','630630':'Velas','630690':'Demás artículos de acampar',
  '630710':'Paños para fregar y artículos similares','630720':'Cinturones y chalecos salvavidas','630790':'Other made-up textile articles',
  '640110':'Calzado impermeable con puntera metálica de protección','640192':'Calzado impermeable que cubre el tobillo sin cubrir la rodilla','640199':'Demás calzado impermeable',
  '640212':'Calzado de esquí y snowboard, de caucho o plástico','640219':'Demás calzado de deporte, de caucho o plástico','640220':'Calzado con tiras fijadas a la suela por tetones','640291':'Demás calzado de caucho o plástico que cubre el tobillo','640299':'Demás calzado de caucho o plástico',
  '640312':'Calzado de esquí y snowboard con corte de cuero','640319':'Demás calzado de deporte con corte de cuero','640320':'Calzado con suela de cuero y tiras sobre el empeine alrededor del dedo gordo','640340':'Demás calzado con corte de cuero y puntera metálica','640351':'Calzado con suela de cuero que cubre el tobillo','640359':'Demás calzado con suela de cuero','640391':'Demás calzado con corte de cuero que cubre el tobillo','640399':'Demás calzado con corte de cuero',
  '640411':'Calzado de deporte, tenis, baloncesto, gimnasia y entrenamiento, con corte textil','640419':'Demás calzado con corte textil y suela de caucho o plástico','640420':'Calzado con corte textil y suela de cuero',
  '640510':'Demás calzado con corte de cuero','640520':'Demás calzado con corte textil','640590':'Demás calzado','640610':'Cortes de calzado y sus partes','640620':'Suelas y tacones de caucho o plástico','640690':'Demás partes de calzado, plantillas, taloneras y polainas',
  '650100':'Cascos sin ahormar ni perfilar, de fieltro','650200':'Cascos trenzados sin ahormar','650400':'Sombreros de paja o de tiras trenzadas','650500':'Sombreros y demás tocados de punto o de tela','650610':'Cascos de seguridad','650691':'Demás tocados de caucho o plástico','650699':'Demás tocados de otras materias','650700':'Desudadores, forros, armazones y viseras para sombreros',
  '660110':'Quitasoles de jardín y similares','660191':'Paraguas con astil telescópico','660199':'Demás paraguas y sombrillas','660200':'Bastones, bastones asiento y similares','660320':'Monturas de paraguas','660390':'Demás partes de paraguas y bastones',
  '900410':'Gafas de sol','900490':'Demás gafas (protectoras y similares)','910211':'Relojes de pulsera eléctricos, indicador mecánico','910212':'Relojes de pulsera eléctricos, indicador optoelectrónico','910219':'Demás relojes de pulsera eléctricos','910221':'Relojes de pulsera automáticos','910229':'Demás relojes de pulsera mecánicos','910291':'Demás relojes de bolsillo eléctricos','910299':'Demás relojes de bolsillo',
  '940421':'Colchones de caucho o plástico celulares','940429':'Colchones de otras materias','940430':'Sacos de dormir','940440':'Edredones y cubrepiés','940490':'Demás artículos de cama (almohadas, cojines)',
  '950691':'Artículos para cultura física, gimnasia o atletismo','950662':'Pelotas inflables','950699':'Demás artículos para deporte o juegos al aire libre',
  '711711':'Gemelos y pasadores de metal común','711719':'Demás bisutería de metal común','711790':'Bisutería de otras materias',
  '392310':'Cajas de plástico','392321':'Sacos y bolsas de polímeros de etileno','392329':'Sacos y bolsas de los demás plásticos','392410':'Vajilla y artículos de mesa o cocina, de plástico','392620':'Prendas y complementos de vestir de plástico','392640':'Estatuillas y artículos de adorno de plástico','392690':'Demás manufacturas de plástico',
  '481910':'Cajas de papel o cartón corrugado','481920':'Cajas plegables de papel o cartón sin corrugar','481940':'Demás sacos y bolsas de papel','482110':'Etiquetas impresas de papel o cartón','490890':'Calcomanías','491191':'Estampas, grabados y fotografías (stickers impresos)',
  '580710':'Etiquetas y escudos tejidos','581091':'Bordados en piezas: de algodón','581092':'Bordados en piezas: de fibras sintéticas o artificiales','581099':'Bordados en piezas: de las demás materias textiles',
  '340510':'Betunes y cremas para calzado o cuero','283699':'Demás carbonatos','382499':'Demás preparaciones químicas','732393':'Artículos de uso doméstico de acero inoxidable','732620':'Manufacturas de alambre de hierro o acero','732690':'Demás manufacturas de hierro o acero','761510':'Artículos de uso doméstico de aluminio',
  '851310':'Lámparas eléctricas portátiles','851762':'Aparatos para recibir y transmitir datos','442110':'Perchas de madera','940171':'Asientos con armazón de metal, con relleno','940179':'Demás asientos con armazón de metal','940320':'Demás muebles de metal','940360':'Demás muebles de madera','940370':'Muebles de plástico',
  '960390':'Demás cepillos','961700':'Termos y demás recipientes isotérmicos','961800':'Maniquíes y artículos similares'
};
Object.assign(DESC_EXTRA, {
  '401519':'Guantes de caucho vulcanizado (demás)','401590':'Demás prendas y complementos de vestir de caucho vulcanizado','401699':'Demás manufacturas de caucho vulcanizado sin endurecer',
  '430310':'Prendas y complementos de vestir de peletería','430390':'Demás artículos de peletería','430400':'Peletería facticia o artificial y sus artículos',
  '560890':'Redes confeccionadas de materia textil (incluidas hamacas de red)','560900':'Artículos de hilados, tiras, cordeles o cuerdas, n.e.p.',
  '630260':'Ropa de tocador o cocina, de tejido con bucles de algodón (toallas)','630291':'Demás ropa de tocador o cocina, de algodón','630293':'Demás ropa de tocador o cocina, de fibras sintéticas o artificiales','630299':'Demás ropa de tocador o cocina, de las demás materias textiles',
  '701399':'Demás artículos de vidrio para mesa, cocina o tocador',
  '711311':'Joyería de plata','711319':'Joyería de los demás metales preciosos','711320':'Joyería de chapado de metal precioso sobre metal común',
  '830810':'Ganchos, corchetes y ojetes de metal común','830820':'Remaches tubulares o con espiga hendida, de metal común','830890':'Demás cierres, hebillas y artículos similares de metal común, y sus partes',
  '911310':'Pulseras para reloj de metal precioso','911320':'Pulseras para reloj de metal común','911390':'Demás pulseras para reloj (cuero, textil, silicona)',
  '392330':'Bombonas, botellas y artículos similares de plástico','392490':'Demás artículos de uso doméstico, higiene o tocador, de plástico',
  '950300':'Juguetes','950621':'Deslizadores de vela','950629':'Demás artículos para deportes acuáticos (tablas de surf, paddle)','950670':'Patines para hielo y patines de ruedas',
  '960500':'Juegos o surtidos de viaje para aseo personal, costura o limpieza del calzado o de prendas','960621':'Botones de plástico sin forrar con materia textil','960622':'Botones de metal común sin forrar con materia textil','960629':'Demás botones','960630':'Formas para botones y demás partes',
  '960711':'Cierres de cremallera con dientes de metal común','960719':'Demás cierres de cremallera','960720':'Partes de cierres de cremallera',
  '961511':'Peines, peinetas, pasadores y similares de caucho endurecido o plástico','961519':'Peines, peinetas, pasadores y similares de otras materias','961590':'Horquillas, rizadores y demás; partes'
});
for (const [k, v] of Object.entries(DESC_EXTRA)) if (!DESC[k]) DESC[k] = v;
Object.assign(CAPITULOS, Object.fromEntries(Object.entries({'40':'Caucho y sus manufacturas','43':'Peletería y sus manufacturas','56':'Guata, cordeles, cuerdas y redes','70':'Vidrio y sus manufacturas','83':'Manufacturas diversas de metal común','96':'Manufacturas diversas','58':'Tejidos especiales, etiquetas y bordados','90':'Instrumentos de óptica','91':'Relojería','94':'Muebles y artículos de cama','95':'Juguetes y artículos para deporte'}).filter(([k])=>!CAPITULOS[k])));

/* ---------- Países de destino (Centroamérica y Panamá) ---------- */
const DESTINOS_BASE = [
  {iso:'GT', nombre:tr('Guatemala'), mcca:true, impuesto:'VAT 12%', digitos:10}, {iso:'SV', nombre:tr('El Salvador'), mcca:true, impuesto:'VAT 13%', digitos:10}, {iso:'HN', nombre:tr('Honduras'), mcca:true, impuesto:tr('Sales tax 15%'), digitos:10},
  {iso:'NI', nombre:tr('Nicaragua'), mcca:true, impuesto:'VAT 15%', digitos:12}, {iso:'CR', nombre:tr('Costa Rica'), mcca:true, impuesto:'VAT 13%', digitos:12}, {iso:'PA', nombre:tr('Panama'), mcca:false, impuesto:'ITBMS 7%', digitos:12}
];
const ISO_DE = {'guatemala':'GT','el salvador':'SV','honduras':'HN','nicaragua':'NI','costa rica':'CR','panama':'PA','estados unidos':'US','usa':'US','eeuu':'US','republica dominicana':'DO','mexico':'MX','chile':'CL','colombia':'CO','peru':'PE','corea del sur':'KR','corea':'KR','taiwan':'TW','china':'CN','reino unido':'GB',
  'eslovenia':'EU','italia':'EU','portugal':'EU','espana':'EU','alemania':'EU','francia':'EU','rumania':'EU','polonia':'EU','union europea':'EU','paises bajos':'EU','belgica':'EU','austria':'EU'};
const MCCA5 = ['GT','SV','HN','NI','CR'];
/* Dígitos del código nacional: los define cada usuario por país (Aranceles o catálogo de Países); estos son solo los valores iniciales */
const DIG_MIN = 6, DIG_MAX = 14;
function limDig(v, def){ const n = parseInt(v, 10); return n >= DIG_MIN && n <= DIG_MAX ? n : def; }
/* Acuerdos conocidos por origen y destino. Siempre hay que confirmar vigencia, lista de desgravación y reglas de origen. */
function notaOrigenDestino(origen, dest, paisesCat){
  const n = norm(origen).trim(); if (!n || !dest) return '';
  /* El origen puede venir como código ISO (así lo guarda el sistema) o como nombre */
  const UE = ['SI','IT','PT','ES','DE','FR','RO','PL','NL','BE','AT','IE','GR','CZ','SK','HU','HR','BG','DK','SE','FI','LT','LV','EE','LU','MT','CY'];
  const up = String(origen).trim().toUpperCase();
  const iso2 = /^[A-Z]{2}$/.test(up) ? (UE.includes(up) ? 'EU' : up) : '';
  const o = iso2 || ISO_DE[n] || (paisesCat || []).map(p=>({n:norm(p.nombre).trim(), iso:String(p.iso || '').toUpperCase()})).find(p=>p.n === n)?.iso || '';
  const cat = (paisesCat || []).find(p=>norm(p.nombre).trim() === n);
  const extra = cat && cat.nota ? ' ' + cat.nota : '';
  if (o === dest) return 'Domestic production.';
  const d5 = MCCA5.includes(dest);
  let t = '';
  if (MCCA5.includes(o) && d5) t = 'Central American Common Market: normally free of import duty with a Central American certificate or declaration of origin';
  else if ((MCCA5.includes(o) && dest === 'PA') || (o === 'PA' && d5)) t = 'Panama and the CACM: preference only for goods included in Panama\'s accession protocol; check the list';
  else if ((o === 'US' || o === 'DO') && d5) t = 'CAFTA-DR: preference may apply if the goods meet its rules of origin (for textiles, usually yarn forward)';
  else if (o === 'US' && dest === 'PA') t = 'Panama–United States Trade Promotion Agreement: preference may apply with proof of origin';
  else if (o === 'EU') t = 'EU–Central America Association Agreement: preference may apply with proof of origin';
  else if (o === 'GB') t = 'UK–Central America Association Agreement: preference may apply with proof of origin';
  else if (o === 'MX') t = d5 ? 'Central America–Mexico FTA: preference may apply with a certificate of origin' : 'Panama–Mexico FTA: preference may apply with a certificate of origin';
  else if (o === 'CL') t = d5 ? 'Central America–Chile FTA: check the tariff elimination schedule' : 'Panama–Chile FTA: check the tariff elimination schedule';
  else if (o === 'KR' && dest !== 'GT') t = 'Korea–Central America FTA: check the tariff elimination schedule';
  else if (o === 'TW' && dest === 'GT') t = 'Guatemala–Taiwan FTA: check the tariff elimination schedule';
  else if (o === 'CO' && ['GT','SV','HN','CR'].includes(dest)) t = 'FTA with Colombia: check the tariff elimination schedule';
  else if (o === 'PE' && ['CR','PA'].includes(dest)) t = 'FTA with Peru: check the tariff elimination schedule';
  else if (o === 'CN' && dest === 'CR') t = 'Costa Rica–China FTA: check the tariff elimination schedule';
  return (t + (t && extra ? '.' : '') + extra).trim();
}

const descDe = c => { const d = digits(c); return DESC[d.slice(0,6)] || DESC[d.slice(0,4)] || DESC[d.slice(0,2)] || ''; };

const TIPOS = [
  [tr('Tops'),[['camiseta',tr('T-shirt, tee, tank top or base layer')],['camisa',tr('Shirt, polo or blouse')],['sudadera',tr('Sweatshirt, hoodie, sweater or fleece')],['chaqueta',tr('Jacket, parka, vest or blazer')]]],
  [tr('Bottoms and one-pieces'),[['pantalon',tr('Pants, shorts, joggers, leggings or bib overalls')],['falda',tr('Skirt')],['vestido',tr('Dress')],['enterizo',tr('Coverall, jumpsuit, romper or baby onesie')],['conjunto',tr('Tracksuit or ski suit')]]],
  [tr('Underwear, sleepwear and swimwear'),[['ropa_interior',tr('Underwear, pajamas or robe')],['brasier',tr('Bra or sports bra')],['traje_bano',tr('Swimsuit or boardshorts')]]],
  [tr('Clothing accessories'),[['calcetines',tr('Socks or hosiery')],['guantes',tr('Gloves')],['bufanda',tr('Scarf, neck gaiter or bandana')],['gorra',tr('Cap, beanie, hat or helmet')],['cinturon',tr('Belt')],['accesorio_pelo',tr('Hair accessory')],['peleteria',tr('Fur or faux fur article')]]],
  [tr('Footwear and accessories'),[['calzado',tr('Footwear: sneakers, boots, shoes, sandals')],['plantilla',tr('Insole or heel cushion')],['cordones',tr('Shoelaces')],['polainas',tr('Gaiters or shoe protectors')],['cuidado_calzado',tr('Shoe care: creams, sprays, brushes')]]],
  [tr('Bags and luggage'),[['mochila',tr('Backpack')],['bolso_viaje',tr('Sports or travel bag')],['bolso_mano',tr('Handbag, purse or crossbody')],['maleta',tr('Suitcase, trolley or briefcase')],['billetera',tr('Wallet, card holder or pocket case')]]],
  [tr('Personal accessories'),[['lentes_sol',tr('Sunglasses')],['reloj',tr('Watch')],['bisuteria',tr('Costume jewelry: bracelets, necklaces, pins')],['llavero',tr('Keychain or lanyard')],['sombrilla',tr('Umbrella')],['botella',tr('Bottle, thermos or tumbler')],['parche',tr('Patch, sticker or decal')],['mascota',tr('Pet accessory')],['correa_reloj',tr('Watch strap or band')]]],
  [tr('Camping, sport and outdoors'),[['tienda',tr('Tent')],['saco',tr('Sleeping bag')],['colchoneta',tr('Sleeping pad, pillow or cushion')],['manta',tr('Blanket')],['toalla',tr('Towel')],['hamaca',tr('Hammock')],['mueble_camping',tr('Camp chair or table')],['linterna',tr('Flashlight or headlamp')],['bastones',tr('Trekking poles')],['equipo_deporte',tr('Sports or fitness equipment')],['magnesio',tr('Climbing chalk')],['patineta',tr('Skateboard and skate parts')]]],
  [tr('Trims and parts'),[['avios',tr('Button, zipper, buckle or eyelet')]]],
  [tr('Packaging and store'),[['bolsa_compra',tr('Shopping bag')],['caja',tr('Box or packaging')],['gancho',tr('Hanger')],['etiqueta',tr('Label or hang tag')],['exhibidor',tr('Display, store fixture or mannequin')]]],
  [tr('Any other product'),[['otro_sac',tr('Any other product: choose its subheading in the SAC')]]]
];
const TIPO_LBL = {}; TIPOS.forEach(g=>g[1].forEach(([k,l])=>{ TIPO_LBL[k] = l; }));
const TIPO_CORTO = {camiseta:'T-shirt',camisa:tr('Shirt or polo'),sudadera:tr('Sweatshirt'),chaqueta:tr('Jacket or vest'),pantalon:tr('Pants or shorts'),falda:tr('Skirt'),vestido:tr('Dress'),enterizo:tr('Coverall'),conjunto:tr('Tracksuit'),ropa_interior:tr('Underwear or pajamas'),brasier:tr('Bra'),traje_bano:tr('Swimsuit'),calcetines:tr('Socks'),guantes:tr('Gloves'),bufanda:tr('Scarf or bandana'),gorra:tr('Cap or headwear'),cinturon:tr('Belt'),calzado:tr('Footwear'),plantilla:tr('Insole'),cordones:tr('Shoelaces'),polainas:tr('Gaiters'),cuidado_calzado:tr('Shoe care'),mochila:tr('Backpack'),bolso_viaje:tr('Sports or travel bag'),bolso_mano:tr('Handbag'),maleta:tr('Suitcase or briefcase'),billetera:tr('Wallet or case'),lentes_sol:tr('Sunglasses'),reloj:tr('Watch'),bisuteria:tr('Costume jewelry'),llavero:tr('Keychain or lanyard'),sombrilla:tr('Umbrella'),botella:tr('Bottle or thermos'),parche:tr('Patch or sticker'),mascota:tr('Pet accessory'),tienda:tr('Tent'),saco:tr('Sleeping bag'),colchoneta:tr('Sleeping pad or pillow'),manta:tr('Blanket'),toalla:tr('Towel'),mueble_camping:tr('Camp chair or table'),linterna:tr('Flashlight'),bastones:tr('Trekking poles'),equipo_deporte:tr('Sports equipment'),magnesio:tr('Climbing chalk'),patineta:tr('Skateboard'),bolsa_compra:tr('Shopping bag'),caja:tr('Box or packaging'),gancho:tr('Hanger'),etiqueta:tr('Label'),exhibidor:tr('Display or mannequin')};
Object.assign(TIPO_CORTO, {otro_sac:tr('Other product'), accesorio_pelo:tr('Hair accessory'), peleteria:tr('Fur article'), correa_reloj:tr('Watch strap'), avios:tr('Trims'), hamaca:tr('Hammock')});
/* Nombres cortos en español para la descripción aduanera */
const TIPO_CORTO_ES = {camiseta:'Camiseta',camisa:'Camisa o polo',sudadera:'Sudadera',chaqueta:'Chaqueta o chaleco',pantalon:'Pantalón o short',falda:'Falda',vestido:'Vestido',enterizo:'Enterizo',conjunto:'Conjunto deportivo',ropa_interior:'Ropa interior o pijama',brasier:'Brasier',traje_bano:'Traje de baño',calcetines:'Calcetines',guantes:'Guantes',bufanda:'Bufanda o bandana',gorra:'Gorra o tocado',cinturon:'Cinturón',calzado:'Calzado',plantilla:'Plantilla',cordones:'Cordones',polainas:'Polainas',cuidado_calzado:'Cuidado de calzado',mochila:'Mochila',bolso_viaje:'Bolso deportivo o de viaje',bolso_mano:'Bolso de mano',maleta:'Maleta o maletín',billetera:'Billetera o estuche',lentes_sol:'Lentes de sol',reloj:'Reloj',bisuteria:'Bisutería',llavero:'Llavero o lanyard',sombrilla:'Sombrilla',botella:'Botella o termo',parche:'Parche o sticker',mascota:'Accesorio para mascota',tienda:'Tienda de campaña',saco:'Saco de dormir',colchoneta:'Colchoneta o almohada',manta:'Manta',toalla:'Toalla',mueble_camping:'Silla o mesa de camping',linterna:'Linterna',bastones:'Bastones',equipo_deporte:'Equipo deportivo',magnesio:'Magnesio',patineta:'Patineta',bolsa_compra:'Bolsa de compra',caja:'Caja o empaque',gancho:'Gancho o percha',etiqueta:'Etiqueta',exhibidor:'Exhibidor o maniquí'};
Object.assign(TIPO_CORTO_ES, {accesorio_pelo:'Accesorio de cabello', peleteria:'Peletería', correa_reloj:'Correa de reloj', avios:'Avíos', hamaca:'Hamaca'});
const TIPO_ALIAS = {
  accesorio_pelo:'pasador scrunchie liga para el pelo cola diadema headband hair clip pinza peineta horquilla bobby pin hair tie',
  peleteria:'faux fur piel sintetica peleteria pelo sintetico fur shearling piel natural',
  correa_reloj:'watch band watch strap correa de reloj pulsera de reloj extensible', avios:'boton botones button zipper cremallera cierre hebilla buckle ojete ojal eyelet remache rivet snap broche jalador',
  hamaca:'hammock hamaca chinchorro',
  otro_sac:'otro producto cualquier other any product sac partida subpartida arancel',
  camiseta:'t-shirt tee playera tank top crop top manga larga base layer primera capa camiseta tecnica running shirt',
  camisa:'polo blusa camisa franela flannel button down guayabera camisa de trabajo',
  sudadera:'hoodie suéter sweater sweatshirt crewneck fleece polar cardigan quarter zip medio cierre pullover',
  chaqueta:'jacket chumpa chamarra parka anorak rompevientos windbreaker impermeable rain jacket puffer plumífero chaleco vest blazer saco softshell',
  pantalon:'pants jeans short bermuda jogger legging tights cargo chino overol de peto bib capri pantaloneta',
  falda:'skirt skort', vestido:'dress',
  enterizo:'coverall overol completo mono jumpsuit romper mameluco onesie pañalero bodysuit',
  conjunto:'tracksuit conjunto deportivo pants y chumpa sudadera y jogger traje de esquí snowsuit',
  ropa_interior:'boxer brief calzoncillo calzón braga panty pijama sleepwear camisón bata albornoz robe camiseta interior',
  brasier:'bra sostén sujetador top deportivo sports bra bralette',
  traje_bano:'swimsuit bikini boardshort pantaloneta de baño vestido de baño swim trunks',
  calcetines:'socks calcetas tines medias crew no show', guantes:'gloves guantes de trabajo mitones',
  bufanda:'scarf cuello neck gaiter buff bandana pañuelo', gorra:'cap hat beanie gorro sombrero bucket trucker visera casco helmet balaclava',
  cinturon:'belt cincho faja',
  calzado:'tenis sneaker zapato bota botín sandalia chancla slide mocasín zueco clog pantufla tacón escolar calzado de seguridad steel toe hiking trail',
  plantilla:'insole plantilla talonera footbed heel cushion', cordones:'laces agujetas pasadores shoelaces',
  polainas:'gaiters polainas protector de calzado spats', cuidado_calzado:'betún crema limpiador cleaner spray protector impermeabilizante cepillo kit de limpieza',
  mochila:'backpack mochila daypack rucksack mochila escolar',
  bolso_viaje:'duffel maletín deportivo cangurera riñonera belt bag waist pack lonchera lunch bag neceser toiletry estuche lapicero pencil case bolsa de gimnasio sling hydration pack bolsa para magnesio chalk bag bolsa para zapatos',
  bolso_mano:'handbag cartera tote crossbody bolso de hombro shoulder bag', maleta:'luggage trolley roller maleta con ruedas maletín briefcase funda de laptop laptop sleeve portafolio',
  billetera:'wallet monedero tarjetero card holder estuche de lentes estuche de celular pasaporte',
  lentes_sol:'sunglasses gafas de sol anteojos lentes oscuros', reloj:'watch smartwatch reloj digital reloj analógico',
  bisuteria:'pulsera collar aretes pin pines anillo bracelet necklace earrings charms', llavero:'keychain llavero lanyard porta gafete key ring',
  sombrilla:'umbrella paraguas sombrilla', botella:'bottle termo thermos tumbler vaso térmico pachón cantimplora hydro flask',
  parche:'sticker calcomanía parche bordado patch decal insignia', mascota:'perro dog collar para perro correa leash arnés harness abrigo para perro mascota pet',
  tienda:'tent carpa tienda de campaña', saco:'sleeping bag bolsa de dormir', colchoneta:'sleeping pad colchoneta colchón inflable almohada pillow cojín cushion',
  manta:'blanket cobija frazada throw', toalla:'towel toalla toalla de playa toalla deportiva',
  mueble_camping:'silla de camping camp chair mesa plegable camp table banco taburete stool',
  linterna:'headlamp linterna frontal flashlight lámpara farol lantern', bastones:'trekking poles bastones hiking poles',
  equipo_deporte:'crash pad colchoneta de escalada yoga mat mat de yoga ligas bandas de resistencia cuerda para saltar rodilleras coderas protecciones skate pelota balón',
  magnesio:'chalk magnesio tiza para escalar liquid chalk', patineta:'skateboard patineta deck tabla ruedas trucks rodamientos skate',
  bolsa_compra:'shopping bag bolsa de papel bolsa de tienda bolsa reutilizable bolsa de regalo', caja:'caja de zapatos shoe box cartón corrugado empaque',
  gancho:'hanger gancho percha colgador', etiqueta:'hang tag etiqueta label etiqueta de precio etiqueta tejida',
  exhibidor:'display exhibidor góndola mueble de tienda shoe wall maniquí mannequin busto'
};
const TIPO_ANTES = {bolsa_magnesio:'bolso_viaje', crash_pad:'equipo_deporte', silla:'mueble_camping'};
function buscarTipos(q, n){
  const w = norm(q).split(/[^a-z0-9]+/).filter(x=>x.length >= 2);
  if (!w.length) return [];
  const out = [];
  for (const [k, lbl] of Object.entries(TIPO_LBL)){
    const hay = norm(lbl + ' ' + (TIPO_ALIAS[k] || ''));
    let sc = 0;
    for (const x of w){ if (new RegExp('\\b' + x).test(hay)) sc += 2; else if (hay.includes(x)) sc += 1; else { sc = -1; break; } }
    if (sc > 0) out.push({k, sc: sc + (norm(lbl).startsWith(w[0]) ? 1 : 0)});
  }
  return out.sort((a,b)=>b.sc - a.sc).slice(0, n || 6).map(x=>x.k);
}
const PRENDAS = ['camiseta','camisa','sudadera','chaqueta','pantalon','falda','vestido','enterizo','conjunto','ropa_interior','brasier','traje_bano','calcetines','guantes','bufanda'];
const BOLSOS = ['mochila','bolso_viaje','bolso_mano','maleta','billetera'];
function grupoTipo(t){
  if (PRENDAS.includes(t)) return 'prenda';
  if (BOLSOS.includes(t)) return 'bolso';
  if (t === 'calzado') return 'calzado';
  if (['plantilla','cordones','polainas','cuidado_calzado'].includes(t)) return 'calzado_acc';
  if (t === 'gorra' || t === 'cinturon') return t;
  if (['lentes_sol','sombrilla','botella','llavero','reloj','bisuteria','parche','mascota','correa_reloj','accesorio_pelo','peleteria','avios'].includes(t)) return 'accesorio';
  if (['tienda','saco','colchoneta','manta','toalla','hamaca','mueble_camping','linterna','bastones','equipo_deporte','magnesio','patineta'].includes(t)) return 'camping';
  if (['bolsa_compra','caja','gancho','etiqueta','exhibidor'].includes(t)) return 'empaque';
  return '';
}
/* Tipos cuyo material se elige con un atributo (no con composición) */
const MAT_ATTR = {cinturon:'materialCinturon', llavero:'materialLlavero', botella:'materialBotella', bisuteria:'materialBisu', bolsa_compra:'materialBolsa', caja:'materialCaja', gancho:'materialGancho', etiqueta:'materialEtiqueta'};
const TIPOS_FORRO = ['chaqueta','pantalon','falda','vestido','enterizo','conjunto','sudadera','mochila','bolso_viaje','bolso_mano','maleta','billetera'];
const CALZ_SIN_FORRO = ['chancla_tetones','slide','zueco','sandalia','acuatico'];
const CALZ_SIN_PLANTILLA = ['chancla_tetones','slide','zueco'];
/* Partes de la composición que aplican según el tipo y lo que ya se eligió (s es opcional) */
function partesDe(t, s){
  const g = grupoTipo(t);
  s = s || {};
  const conRelleno = () => t === 'saco' || (t === 'chaqueta' && !['chaleco','blazer','reflectivo'].includes(s.hechura) && ['plumon','sintetico'].includes(s.relleno_tipo));
  const conForro = () => TIPOS_FORRO.includes(t) && !!s.tieneForro;
  if (g === 'prenda'){ const p = ['exterior']; if (conForro()) p.push('forro'); if (conRelleno()) p.push('relleno'); return p; }
  if (g === 'calzado'){ const p = ['corte','suela']; if (!CALZ_SIN_FORRO.includes(s.estiloCalz)) p.push('forro'); if (!CALZ_SIN_PLANTILLA.includes(s.estiloCalz)) p.push('plantilla'); return p; }
  if (g === 'bolso'){ const p = ['exterior']; if (conForro()) p.push('forro'); return p; }
  if (t === 'saco') return ['exterior','relleno'];
  if (['tienda','gorra','manta','toalla','colchoneta','polainas'].includes(t)) return ['exterior'];
  if (t) return ['material'];
  return [];
}
const PARTE_LBL = {exterior:tr('Outer fabric or surface'),forro:tr('Lining'),relleno:tr('Fill'),corte:tr('Upper'),suela:tr('Sole'),plantilla:tr('Insole'),material:tr('Main material')};
const PARTE_PH = {exterior:tr('E.g. 100% polyester, or shell: 100% nylon'),forro:tr('E.g. 100% polyester'),relleno:tr('E.g. 90% down 10% feather'),corte:tr('E.g. 60% leather 40% textile, excluding reinforcements and trims'),suela:tr('E.g. 100% rubber, or EVA and rubber'),plantilla:tr('E.g. EVA with textile cover'),material:tr('E.g. leather, stainless steel, nylon')};

/* ---------- Composición ---------- */
const FIBRAS = [
  {g:'lana', re:/\b(lana|wool|merino|cachemira?|cashmere|alpaca|mohair|angora|wo)\b/g},
  {g:'seda', re:/\b(seda|silk)\b/g},
  {g:'algodon', re:/\b(algodon|cotton|co)\b/g},
  {g:'vegetal', re:/\b(lino|linen|canamo|hemp|yute|jute|ramio|ramie|li)\b/g},
  {g:'sintetica', re:/\b(poliester|polyester|rpet|nylon|nilon|poliamida|polyamide|acrilico|acrylic|elastano|elastane|spandex|lycra|elastodieno|polipropileno|polypropylene|aramida|aramid|olefina|olefin|polietileno|polyethylene|pes|pa|pl|ea|el|pan|pp)\b/g},
  {g:'artificial', re:/\b(viscosa|viscose|rayon|modal|lyocell|tencel|acetato|acetate|triacetato|cupro|cv|cmd)\b/g},
  {g:'cuero', re:/\b(cuero|leather|piel|gamuza|suede|nubuck|nobuck)\b/g}
];
const MAT_CALZ = [
  {g:'plastico', re:/\b(cuero sintetico|piel sintetica|synthetic leather|faux leather|pu leather|vegan leather|leatherette|sinteticos?|synthetics?|pu|tpu|tpr|kpu|pvc|vinilo|vinyl|caucho|rubber|goma|hule|latex|eva|plasticos?|plastics?|tr|phylon|poliuretano|polyurethane|silicona|silicone|crepe|policarbonato|polycarbonate|tritan|abs)\b/g},
  {g:'cuero', re:/\b(cuero|leather|piel|suede|gamuza|nubuck|nobuck|napa|nappa|charol|patent|ante|carnaza)\b/g},
  {g:'textil', re:/\b(textil|textile|tela|fabric|mesh|malla|canvas|lona|nylon|poliester|polyester|rpet|poliamida|polyamide|acrilico|acrylic|elastano|elastane|spandex|lycra|viscosa|viscose|rayon|modal|tencel|lino|linen|seda|silk|knit|flyknit|tejido|jersey|microfibra|microfiber|neopreno|neoprene|lana|wool|merino|algodon|cotton|fieltro|felt|corduroy|pana|denim|mezclilla|cordura|ripstop|fleece|polar|terry|felpa|oxford|polipropileno|polypropylene|satin|saten|elastico|lyocell|elastano)\b/g},
  {g:'otro', re:/\b(madera|wood|corcho|cork|metal|metalico|acero|steel|inoxidable|stainless|aluminio|aluminum|aluminium|hierro|iron|zinc|bronce|brass|laton|titanio|titanium|yute|jute|papel|paper|carton|cardboard|cartulina|kraft|vidrio|glass|cristal|paja|straw|palma|rafia|mdf|arce|maple|bambu|bamboo|pino|alambre|wire|cromo)\b/g}
];
const FIB_LBL = {lana:'wool',seda:'silk',algodon:'cotton',vegetal:tr('vegetable fiber (linen, hemp)'),sintetica:tr('synthetic fiber'),artificial:tr('artificial fiber'),cuero:'leather',otra:tr('unidentified material')};
const MAT_LBL = {plastico:tr('rubber or plastics'),cuero:'leather',textil:'textile',otro:tr('other material'),otra:'unidentified',caucho:tr('rubber or plastics')};
const MAT_STOP = new Set(('shell body cuerpo exterior forro lining relleno fill filling upper sole suela outsole insole plantilla midsole entresuela and with the con del los las por para sin recycled reciclado reciclada organic organico organica virgin main trim trims rib ribete principal capa layer fabric material materials materiales total other others demas parte partes superficie surface interior bonded laminado laminated coated recubierto without full grain flor split top bottom excluding contar refuerzos adornos accessories accesorios hood capucha pocket pocketing bolsillo bolsillos contrast contraste panel paneles power goose duck down plumon pluma plumas feather feathers fiber fibra fibras blend mezcla mix approx aprox aproximadamente weight peso gsm denier oz yarn hilo thread face back backing soporte membrane membrana dryvent futurelight goretex gore insulation aislante padding guata primaloft thermoball heatseeker vibram ortholite cushion foam espuma molded moldeado injected inyectado vulcanized vulcanizado cemented stitched cosido parts one outer inner lined unlined logo logos print estampado bci grs rcs eco otros otras resto rest').split(' '));
const MAT_AMBIGUAS = {microfibra:'Microfiber can be textile or synthetic (PU): say which', microfiber:'Microfiber can be textile or synthetic (PU): say which', microfibre:'Microfiber can be textile or synthetic (PU): say which', neopreno:'Neoprene: counts as textile if the fabric faces out; if the rubber is exposed, as rubber or plastics', neoprene:'Neoprene: counts as textile if the fabric faces out; if the rubber is exposed, as rubber or plastics'};
const MAT_EQUIV = [['cuero','Natural leather (hide, suede, nubuck)'],['sintetico','Synthetic: rubber or plastics (PU, PVC, TPU)'],['caucho','Rubber or EVA'],['textil','Textile (fabric, canvas, mesh)'],['algodon','Cotton'],['poliester','Polyester'],['nylon','Nylon or polyamide'],['elastano','Elastane or spandex'],['acrilico','Acrylic'],['viscosa','Viscose or rayon'],['lana','Wool'],['seda','Silk'],['lino','Linen or other vegetable fiber'],['metal','Metal'],['madera','Wood, cork or other material']];
let SINONIMOS = {}, _prepMemo = new Map(), _vocab = null, _known = null;
/* Términos comerciales frecuentes y a qué material equivalen para el SAC: el
   cuero sintético, el PU o la "gamuza sintética" son plástico; el ante, el
   nobuk o la vaqueta son cuero; las telas por su nombre comercial son textil.
   Primero van las frases largas para que "synthetic suede" no se lea "suede". */
const SINONIMOS_BASE = {
  'synthetic suede':'pu', 'faux suede':'pu', 'micro suede':'pu', 'microsuede':'pu', 'gamuza sintetica':'pu', 'ante sintetico':'pu',
  'synthetic leather':'pu', 'faux leather':'pu', 'vegan leather':'pu', 'pu leather':'pu', 'cuero sintetico':'pu', 'piel sintetica':'pu',
  'bonded leather':'pu', 'leatherette':'pu', 'pleather':'pu', 'polyurethane leather':'pu', 'simil cuero':'pu', 'similcuero':'pu', 'cuerina':'pu', 'ecocuero':'pu',
  'coated fabric':'pvc', 'pu coated':'pu', 'tpu film':'tpu', 'rubber sole':'rubber', 'gum rubber':'rubber', 'crepe rubber':'rubber',
  'full grain leather':'leather', 'full grain':'leather', 'top grain leather':'leather', 'top grain':'leather', 'split leather':'leather', 'grain leather':'leather',
  'cowhide':'leather', 'cow leather':'leather', 'calfskin':'leather', 'goatskin':'leather', 'sheepskin':'leather', 'pigskin':'leather', 'lambskin':'leather',
  'vaqueta':'cuero', 'becerro':'cuero', 'carnaza':'cuero', 'nobuk':'nubuck', 'nubuk':'nubuck', 'oiled leather':'leather', 'waxed leather':'leather',
  'phylon':'eva', 'ip eva':'eva', 'md':'eva', 'tpe':'tpr', 'kraton':'tpr',
  'twill':'textile', 'oxford':'textile', 'taslan':'textile', 'tricot':'textile', 'sherpa':'polyester', 'corduroy':'textile', 'pana':'textil',
  'terry':'textile', 'french terry':'textile', 'velour':'textile', 'velvet':'textile', 'terciopelo':'textil', 'chenille':'textile', 'suedette':'textile',
  'flyknit':'knit', 'primeknit':'knit', 'engineered mesh':'mesh', 'air mesh':'mesh', 'spacer mesh':'mesh', 'lycra':'elastane', 'dralon':'acrylic',
  'tencel':'lyocell', 'lyocell':'viscose', 'cupro':'viscose', 'bamboo viscose':'viscose', 'recycled polyester':'polyester', 'rpet':'polyester',
};
SINONIMOS = { ...SINONIMOS_BASE };
function setSinonimos(lista){
  SINONIMOS = { ...SINONIMOS_BASE };
  (lista || []).forEach(x=>{ const k = norm(x.palabra).trim(); if (k && x.equivale) SINONIMOS[k] = x.equivale; });
  _prepMemo = new Map();
}
/* Categoría de un material escrito (una fila de la composición) para mostrarla
   junto al campo: cuero, textil, caucho o plástico (sintético)… */
const CLASE_LBL = {cuero:tr('Leather'), textil:tr('Textile'), plastico:tr('Rubber or plastics'), metal:tr('Metal'), madera:tr('Wood or cork'), papel:tr('Paper'), vidrio:tr('Glass'), paja:tr('Straw')};
function claseTexto(txt){
  const t = prepMat(txt || '').s;
  if (!t.trim()) return null;
  const pesos = pesosDe(t, CLASES_MAT);
  let clase = null, best = -1;
  for (const [k, n] of Object.entries(pesos)) if (k !== 'otra' && n > best){ best = n; clase = k; }
  if (!clase) return null;
  const sint = clase === 'plastico' && !/\b(caucho|rubber|goma|hule|latex|eva|tpr)\b/.test(t);
  return {clase, lbl: sint ? tr('Synthetic (plastics)') : CLASE_LBL[clase]};
}
function vocabMat(){
  if (_vocab) return _vocab;
  const set = new Set();
  FIBRAS.concat(MAT_CALZ).forEach(f=>{
    f.re.source.replace(/^\\b\(/, '').replace(/\)\\b$/, '').split('|').forEach(w=>{
      if (/^[a-z]{4,}$/.test(w)) set.add(w);
      const m = w.match(/^([a-z]{4,})(s|es)\?$/); if (m) set.add(m[1]);
    });
  });
  _vocab = [...set];
  _known = FIBRAS.concat(MAT_CALZ).map(f=>new RegExp('^' + f.re.source.replace(/\\b/g, '') + '$'));
  return _vocab;
}
function conocida(w){ vocabMat(); return _known.some(r=>r.test(w)); }
function lev(a, b, lim){
  if (Math.abs(a.length - b.length) > lim) return lim + 1;
  let prev = Array.from({length:b.length + 1}, (_, j)=>j);
  for (let i = 1; i <= a.length; i++){
    const cur = [i]; let min = i;
    for (let j = 1; j <= b.length; j++){ cur[j] = Math.min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (a[i-1] === b[j-1] ? 0 : 1)); if (cur[j] < min) min = cur[j]; }
    if (min > lim) return lim + 1;
    prev = cur;
  }
  return prev[b.length];
}
/* Lee lo que la gente escribe de verdad: sinónimos aprendidos, errores de dedo, números sin %, abreviaturas */
function prepMat(raw){
  const key = String(raw == null ? '' : raw);
  if (_prepMemo.has(key)) return _prepMemo.get(key);
  let s = norm(key).replace(/[\/+&]/g, ' , ').replace(/\s+/g, ' ');
  const cambios = [], desconocidas = [], ambiguas = [];
  for (const [k, v] of Object.entries(SINONIMOS)){
    const re = new RegExp('(^|[^a-z])' + k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![a-z])', 'g');
    if (re.test(s)){ s = s.replace(re, (m, p)=>p + v); cambios.push({de:k, a:v, aprendido:true}); }
  }
  const vocab = vocabMat();
  s = s.replace(/[a-z]{3,}/g, w=>{
    if (MAT_STOP.has(w) || conocida(w)) { if (MAT_AMBIGUAS[w]) ambiguas.push(w); return w; }
    if (w.length >= 4){
      const lim = w.length >= 7 ? 2 : 1;
      let best = null, bd = lim + 1, empate = false;
      for (const v of vocab){ const d = lev(w, v, lim); if (d < bd){ bd = d; best = v; empate = false; } else if (d === bd && best && v !== best) empate = true; }
      if (best && bd <= lim && !empate){ cambios.push({de:w, a:best}); return best; }
    }
    desconocidas.push(w); return w;
  });
  if (!/%/.test(s)){
    const re = /(^|[^\d.,a-z])(\d{1,3}(?:[.,]\d+)?)(?![\d.,]*\s*(?:%|fill|g|gr|gsm|oz|den|d|mm|cm)\b)/g;
    const nums = [...s.matchAll(re)].map(m=>parseFloat(m[2].replace(',', '.')));
    const sum = nums.reduce((a,b)=>a+b, 0);
    if (nums.length && Math.abs(sum - 100) <= 1 && nums.every(n=>n <= 100)){ s = s.replace(re, (m, p, n)=>p + n + '%'); cambios.push({pct:true}); }
  }
  const out = {s, cambios, desconocidas:[...new Set(desconocidas)], ambiguas:[...new Set(ambiguas)]};
  if (_prepMemo.size > 3000) _prepMemo = new Map();
  _prepMemo.set(key, out);
  return out;
}
function matchesIn(txt, lista){
  const out = [];
  for (const f of lista){ f.re.lastIndex = 0; let m; while ((m = f.re.exec(txt))) out.push({g:f.g, i:m.index, e:m.index + m[0].length, w:m[0]}); }
  out.sort((a,b)=>a.i - b.i || (b.e - b.i) - (a.e - a.i));
  const res = []; let end = -1;
  for (const x of out){ if (x.i < end) continue; res.push(x); end = x.e; }
  return res;
}
function paresDe(body, lista){
  const pares = [];
  const pcts = [...body.matchAll(/(\d+(?:[.,]\d+)?)\s*%/g)];
  if (!pcts.length){ const f = matchesIn(body, lista)[0]; if (f) pares.push({pct:100, g:f.g, w:f.w, implicito:true}); return pares; }
  const antes = matchesIn(body.slice(0, pcts[0].index), lista).length > 0;
  pcts.forEach((m,i)=>{
    const val = parseFloat(m[1].replace(',','.'));
    let f;
    if (antes){ const ini = i > 0 ? pcts[i-1].index + pcts[i-1][0].length : 0; const fs = matchesIn(body.slice(ini, m.index), lista); f = fs[fs.length-1]; }
    else { const fin = i+1 < pcts.length ? pcts[i+1].index : body.length; f = matchesIn(body.slice(m.index + m[0].length, fin), lista)[0]; }
    pares.push({pct:val, g:f ? f.g : 'otra', w:f ? f.w : ''});
  });
  return pares;
}
function pesosDe(body, lista){ const pesos = {}; paresDe(body, lista).forEach(p=>{ pesos[p.g] = (pesos[p.g] || 0) + p.pct; }); return pesos; }
const RE_LABELS = /\b(tela exterior|tela principal|parte superior|shell|exterior|outer|outside|body|cuerpo|principal|main|face|self|lining|forro|relleno|fill|filling|insulation|aislante|padding|guata|trim|ribete|rib|pocketing|pocket|bolsillos?|hood|capucha|contrast|contraste|paneles|panel|upper|outsole|sole|suela)\s*[:=]/g;
const LBL_MAIN = /^(shell|exterior|outer|outside|body|cuerpo|principal|main|face|self|tela exterior|tela principal)$/;
const LBL_SEC = /^(lining|forro|relleno|fill|filling|insulation|aislante|padding|guata|trim|ribete|rib|pocket|pocketing|bolsillo|bolsillos|hood|capucha|contrast|contraste|panel|paneles)$/;
function parseComp(raw){
  const pr = prepMat(raw);
  let s = pr.s.trim();
  if (!s) return null;
  s = s.replace(RE_LABELS, '\n$1:');
  const segs = s.split(/[\n;|]+/).map(x=>x.trim()).filter(Boolean).map(p=>{
    const m = p.match(/^([a-z][a-z ]{1,20}?)\s*:\s*(.*)$/);
    const body = m ? m[2] : p;
    return {label: m ? m[1].trim() : '', body, fibras: matchesIn(body, FIBRAS)};
  });
  const seg = segs.find(x=>LBL_MAIN.test(x.label) && (x.fibras.length || /%/.test(x.body)))
    || segs.find(x=>!LBL_SEC.test(x.label) && (x.fibras.length || /%/.test(x.body)))
    || segs.find(x=>x.fibras.length);
  if (!seg) return null;
  const pesos = pesosDe(seg.body, FIBRAS);
  const pred = fibraPred(pesos);
  if (!pred) return null;
  return {pesos, pred, segmento: seg.label || '', usoSegmento: segs.length > 1, prep:pr};
}
const FAM_ORDER = ['seda','lana','algodon','vegetal','manmade'];
function fibraPred(p){
  const tex = {seda:p.seda||0, lana:p.lana||0, algodon:p.algodon||0, vegetal:p.vegetal||0, manmade:(p.sintetica||0)+(p.artificial||0)};
  const totalTex = Object.values(tex).reduce((a,b)=>a+b,0);
  const cuero = p.cuero||0, otra = p.otra||0;
  if (cuero > 0 && cuero >= totalTex && cuero >= otra) return {grupo:'cuero', familia:'cuero', pct:cuero};
  if (totalTex === 0) return otra ? {grupo:'otra', familia:'otra', pct:otra} : null;
  let best = null;
  for (const k of FAM_ORDER){ if (tex[k] > 0 && (!best || tex[k] >= tex[best])) best = k; }
  if (otra > tex[best]) return {grupo:'otra', familia:'otra', pct:otra};
  let grupo = best;
  if (best === 'manmade') grupo = (p.sintetica||0) >= (p.artificial||0) ? 'sintetica' : 'artificial';
  const empate = FAM_ORDER.filter(k=>k !== best && tex[k] === tex[best] && tex[k] > 0).length > 0;
  const mezclaMM = best === 'manmade' && (p.sintetica||0) > 0 && (p.artificial||0) > 0;
  return {grupo, familia:best, pct:Math.round(tex[best]*100)/100, empate, mezclaMM};
}
function parseMat(raw, modo){
  const pr = prepMat(raw);
  const s = pr.s.trim();
  if (!s) return null;
  if (!/%/.test(s)){
    const gs = [...new Set(matchesIn(s, MAT_CALZ).map(m=>m.g))];
    if (gs.length > 1 && modo !== 'suela') return {pesos:{}, pred:null, mixto:true, grupos:gs, prep:pr};
  }
  const pesos = pesosDe(s, MAT_CALZ);
  let g = null, best = -1;
  for (const [k,v] of Object.entries(pesos)) if (k !== 'otra' && v > best){ best = v; g = k; }
  if (!g) return {pesos, pred:null, prep:pr};
  let cat = g;
  if (modo === 'suela') cat = g === 'plastico' ? 'caucho' : g === 'cuero' ? 'cuero' : 'otro';
  return {pesos, pred:cat, pct:best, mixto: Object.keys(pesos).filter(k=>k !== 'otra').length > 1, prep:pr};
}
function resumenMat(pm){ return Object.entries(pm.pesos || {}).filter(([k])=>k !== 'otra').sort((a,b)=>b[1] - a[1]).map(([k,v])=>MAT_LBL[k] + ' ' + Math.round(v*10)/10 + '%').join(', '); }
function textoNormalizado(raw, modo){
  const pr = prepMat(raw); const lista = modo === 'fibra' ? FIBRAS : MAT_CALZ;
  const pares = paresDe(pr.s, lista).filter(p=>p.w);
  if (!pares.length) return '';
  return pares.map(p=>Math.round(p.pct*10)/10 + '% ' + p.w).join(', ');
}
function pickSub(opts, pred){
  if (!pred) return null;
  if (opts[pred.grupo]) return opts[pred.grupo];
  if (pred.familia === 'manmade' && opts.manmade) return opts.manmade;
  return opts.demas || null;
}
/* Materias que salen de la composición y mandan sobre lo marcado a mano */
function predParte(s, parte, modo){ const v = (s.comp || {})[parte]; if (!v || !String(v).trim()) return null; const pm = parseMat(v, modo || 'corte'); return pm && pm.pred ? pm : null; }
const METAL_RE = /\b(metal|metalic[oa]|acero|steel|inoxidable|stainless|aluminio|aluminum|aluminium|hierro|iron|zinc|bronce|brass|laton|titanio|titanium)\b/;
function matDerivado(s, parte, mapa){
  const v = (s.comp || {})[parte]; if (!v || !String(v).trim()) return null;
  const t = prepMat(v).s;
  if (mapa.paja && /\b(paja|straw)\b/.test(t)) return 'paja';
  if (mapa.metal && METAL_RE.test(t) && !/\b(cuero|leather|nylon|poliester|polyester|plastic|plastico|pvc|silicon)/.test(t)) return 'metal';
  const pm = parseMat(v, 'corte'); if (!pm || !pm.pred) return null;
  return mapa[pm.pred] || null;
}
const CLASES_MAT = [
  {g:'plastico', re:/\b(cuero sintetico|piel sintetica|synthetic leather|faux leather|pu leather|vegan leather|sinteticos?|synthetics?|pu|tpu|tpr|pvc|vinilo|vinyl|caucho|rubber|goma|hule|latex|eva|plasticos?|plastics?|poliuretano|polyurethane|silicona|silicone|policarbonato|polycarbonate|tritan|abs)\b/g},
  {g:'cuero', re:/\b(cuero|leather|piel|suede|gamuza|nubuck|nobuck|napa|nappa|charol|patent|ante|carnaza)\b/g},
  {g:'metal', re:/\b(metal|metalic[oa]|acero|steel|inoxidable|stainless|aluminio|aluminum|aluminium|hierro|iron|zinc|bronce|brass|laton|titanio|titanium|alambre|wire|cromo)\b/g},
  {g:'madera', re:/\b(madera|wood|mdf|arce|maple|bambu|bamboo|pino|corcho|cork)\b/g},
  {g:'papel', re:/\b(papel|paper|carton|cartulina|cardboard|kraft)\b/g},
  {g:'vidrio', re:/\b(vidrio|glass|cristal)\b/g},
  {g:'paja', re:/\b(paja|straw|palma|rafia)\b/g},
  {g:'textil', re:/\b(textil|textile|tela|fabric|mesh|malla|canvas|lona|nylon|poliester|polyester|rpet|poliamida|polyamide|acrilico|acrylic|elastano|elastane|spandex|lycra|viscosa|viscose|rayon|modal|tencel|lino|linen|seda|silk|knit|tejido|jersey|microfibra|neopreno|lana|wool|algodon|cotton|fieltro|felt|denim|mezclilla|cordura|ripstop|fleece|polar|felpa|polipropileno|polypropylene|satin|saten|elastico|yute|jute)\b/g}
];
function claseMat(s, parte){
  const v = (s.comp || {})[parte]; if (!v || !String(v).trim()) return null;
  const t = prepMat(v).s;
  const pesos = pesosDe(t, CLASES_MAT);
  let pred = null, best = -1;
  for (const [k, n] of Object.entries(pesos)) if (k !== 'otra' && n > best){ best = n; pred = k; }
  return pred ? {pred, pesos, corrugado:/\bcorrugad|corrugated/.test(t), aluminio:/\b(aluminio|aluminum|aluminium)\b/.test(t)} : null;
}
function edadDe(s){ return s.edad === 'bebe' ? 'bebe' : (s.edadNac || (['adulto','nino'].includes(s.edad) ? s.edad : '')); }
/* Solo se pregunta hombre/mujer cuando la subpartida lo separa */
function requiereGenero(s){
  const t = s.tipo; if (grupoTipo(t) !== 'prenda' || s.edad === 'bebe') return false;
  const tej = t === 'calcetines' ? 'punto' : (s.tejido || ({camiseta:'punto', sudadera:'punto', conjunto:'punto', traje_bano:'punto', ropa_interior:'punto', guantes:'punto', bufanda:'punto'})[t] || 'plano');
  if (['falda','vestido','brasier','calcetines','guantes','bufanda'].includes(t)) return false;
  if (t === 'chaqueta') return !(tej === 'punto' && ['chaleco','reflectivo'].includes(s.hechura));
  if (t === 'ropa_interior') return !(tej === 'punto' && s.prendaInt === 'camiseta_int');
  if (t === 'conjunto') return tej === 'plano' && !s.esqui;
  if (['camisa','pantalon','traje_bano'].includes(t)) return true;
  if (t === 'camiseta') return tej === 'plano' || !!s.polo;
  return tej === 'plano';
}
const OPT_LBL = {lana:'wool',seda:'silk',algodon:'cotton',sintetica:tr('synthetic fiber'),artificial:tr('artificial fiber'),manmade:tr('synthetic or artificial fiber'),demas:tr('other textile material')};

/* ---------- Atributos con dependencias ---------- */
const NO_TOBILLO = ['sandalia','chancla_tetones','slide','mocasin','pantufla','zueco','tacon','danza'];
const SI_TOBILLO = ['bota','botin','esqui','bota_lluvia'];
const PUNTERA_EST = ['bota','botin','zapato','tenis','seguridad','bota_lluvia','senderismo'];
const SOLO_ADULTO = {seguridad:tr('Industrial safety footwear is for adults.'), tacon:tr('There are no high heels for babies.'), tacos:tr('There is no cleated or spiked footwear for babies.'), esqui:tr('There are no ski or snowboard boots for babies.')};
const MSG_PUNTERA = tr('Protective toe caps are for adult work footwear.');
const offBotella = (s, tipo) => { const v = prepMat((s.comp || {}).material || '').s; if (!v.trim()) return null;
  const es = /\b(aluminio|aluminum|aluminium)\b/.test(v) ? 'aluminio' : /\b(acero|steel|inoxidable|stainless)\b/.test(v) ? 'acero' : (parseMat(v, 'corte') || {}).pred === 'plastico' ? 'plastico' : '';
  return es && es !== tipo ? tr('The material composition says {0}.', [({aluminio:'aluminum', acero:tr('stainless steel'), plastico:'plastic'})[es]]) : null; };
const motComp = (parte, s, modo) => { const pm = predParte(s, parte, modo); return tr('Taken from the composition {0}{1}. If it is wrong, fix the composition.', [({corte:tr('of the upper'), suela:tr('of the sole'), exterior:tr('of the outer fabric'), material:tr('of the material')})[parte], pm ? ' (' + resumenMat(pm) + ')' : '']); };
const noPlasticoCorte = s => { const pm = predParte(s, 'corte'); return pm && pm.pred !== 'plastico' ? tr('The upper composition is {0}, not rubber or plastics.', [MAT_LBL[pm.pred]]) : null; };
const ATTRS = [
  {id:'tejido', label:tr('Fabric'), tipo:'seg', aplica:s=>grupoTipo(s.tipo) === 'prenda' && s.tipo !== 'brasier' || (s.tipo === 'cinturon' && s.materialCinturon === 'textil'),
    ops:[{v:'punto', l:tr('Knitted')}, {v:'plano', l:tr('Woven'), off:s=> s.tipo === 'camiseta' ? tr('A T-shirt is knitted; if the fabric is woven, choose "Shirt, polo or blouse".') : s.tipo === 'calcetines' ? tr('Socks are knitted.') : null}]},
  {id:'edad', label:tr('Who it is for'), tipo:'seg', def:'general', aplica:s=>grupoTipo(s.tipo) === 'prenda' && s.tipo !== 'brasier',
    ops:[{v:'general', l:tr('Child, youth or adult')},
      {v:'bebe', l:tr('Baby (up to 86 cm tall)'), off:s=> s.tipo === 'chaqueta' && ['reflectivo','blazer'].includes(s.hechura) ? tr('Not made in baby sizes.') : null}]},
  {id:'genero', label:tr('Gender'), ayuda:tr('this garment is classified differently for men and women'), tipo:'seg', aplica:s=>requiereGenero(s) || ['falda','vestido','brasier'].includes(s.tipo) && s.edad !== 'bebe',
    fijo:s=>['falda','vestido','brasier'].includes(s.tipo) ? 'F' : null, fijoMotivo:tr('This garment is always classified as women\'s.'),
    ops:[{v:'M', l:tr('Men or boys')}, {v:'F', l:tr('Women or girls')}, {v:'U', l:tr('Unisex (anyone)')}]},
  {id:'hechura', label:tr('Construction'), tipo:'seg', aplica:s=>s.tipo === 'chaqueta',
    ops:[{v:'chaqueta', l:tr('Jacket, anorak, parka or windbreaker')}, {v:'chaleco_relleno', l:tr('Padded or insulated vest')}, {v:'chaleco', l:tr('Vest without fill')},
      {v:'reflectivo', l:tr('Reflective safety vest'), off:s=> ['nino','bebe'].includes(edadDe(s)) ? tr('It is work equipment for adults.') : null},
      {v:'blazer', l:tr('Suit jacket or blazer'), off:s=> s.edad === 'bebe' ? tr('Not made in baby sizes.') : null}]},
  {id:'hechuraSud', label:tr('Construction'), tipo:'seg', aplica:s=>s.tipo === 'sudadera',
    ops:[{v:'pullover', l:tr('Pullover or hoodie, no full zip')}, {v:'cierre', l:tr('Full zip')}, {v:'chaqueta_fleece', l:tr('Fleece jacket worn as outerwear (pockets, lining or high collar)')}]},
  {id:'polo', tipo:'check', label:tr('Has a collar and a buttoned placket at the neck (polo style)'), aplica:s=>s.tipo === 'camiseta'},
  {id:'prendaInt', label:tr('Garment'), tipo:'seg', aplica:s=>s.tipo === 'ropa_interior',
    ops:[{v:'interior', l:tr('Briefs, boxers or panties')}, {v:'pijama', l:tr('Pajamas or nightgown')}, {v:'camiseta_int', l:tr('Undershirt')}, {v:'bata', l:tr('Robe or bathrobe')}]},
  {id:'tipoBufanda', label:tr('Garment'), tipo:'seg', aplica:s=>s.tipo === 'bufanda',
    ops:[{v:'bufanda', l:tr('Scarf, neck warmer or gaiter')}, {v:'bandana', l:tr('Square handkerchief or bandana, up to 60 cm per side')}]},
  {id:'recubierta', tipo:'check', label:tr('Fabric coated or laminated with visible plastic or rubber (membrane such as DryVent, Gore-Tex, PU)'), aplica:s=>['camiseta','camisa','sudadera','chaqueta','pantalon','guantes','conjunto','enterizo'].includes(s.tipo) && s.hechura !== 'blazer',
    offCheck:s=> s.edad === 'bebe' ? tr('Baby garments go in 6111 or 6209 even if the fabric is coated.') : null},
  {id:'relleno_tipo', label:tr('Fill'), tipo:'seg', aplica:s=>(s.tipo === 'chaqueta' && ['','chaqueta','chaleco_relleno'].includes(s.hechura || '')) || s.tipo === 'saco', info:true,
    ops:[{v:'ninguno', l:tr('No fill'), off:s=> s.hechura === 'chaleco_relleno' ? tr('A padded vest has fill.') : s.tipo === 'saco' ? tr('A sleeping bag has fill.') : null}, {v:'plumon', l:tr('Down or feather')}, {v:'sintetico', l:tr('Synthetic')}]},
  {id:'tieneForro', tipo:'check', label:tr('Has a lining'), aplica:s=>TIPOS_FORRO.includes(s.tipo) && s.hechura !== 'reflectivo', info:true},
  {id:'manga', label:tr('Sleeve'), tipo:'seg', aplica:s=>['camiseta','camisa','sudadera','vestido','chaqueta'].includes(s.tipo), info:true, soloNac:true,
    ops:[{v:'sin', l:tr('Sleeveless')}, {v:'corta', l:tr('Short')}, {v:'larga', l:tr('Long')}]},
  {id:'esqui', tipo:'check', label:tr('It is a ski or snowboard suit'), aplica:s=>s.tipo === 'conjunto'},
  {id:'guanteDeporte', tipo:'check', label:tr('Leather glove specially designed for sports'), aplica:s=>s.tipo === 'guantes' && s._matGuante === 'cuero'},
  {id:'estiloCalz', label:tr('Footwear style'), tipo:'select', aplica:s=>s.tipo === 'calzado',
    ops:[{v:'tenis', l:tr('Sneaker')}, {v:'senderismo', l:tr('Hiking or trekking')}, {v:'bota', l:tr('Boot')}, {v:'botin', l:tr('Ankle boot')},
      {v:'zapato', l:tr('Closed shoe (dress, casual, school)')}, {v:'tacon', l:tr('High-heeled shoe'), off:s=> edadDe(s) === 'bebe' ? SOLO_ADULTO.tacon : null}, {v:'mocasin', l:tr('Moccasin, loafer or boat shoe')},
      {v:'sandalia', l:tr('Sandal')}, {v:'slide', l:tr('Slide')}, {v:'chancla_tetones', l:tr('Rubber or plastic flip-flop (toe post)'), off:noPlasticoCorte}, {v:'zueco', l:tr('Molded clog')}, {v:'acuatico', l:tr('Water shoe')}, {v:'pantufla', l:tr('Slipper or house shoe')}, {v:'danza', l:tr('Dance shoe')}, {v:'roller', l:tr('With wheels (roller, Heelys type)')}, {v:'cubrecalzado', l:tr('Overshoe (worn over other footwear)')},
      {v:'seguridad', l:tr('Safety or industrial footwear'), off:s=> ['bebe','nino'].includes(edadDe(s)) ? SOLO_ADULTO.seguridad : null},
      {v:'bota_lluvia', l:tr('Rain boot'), off:noPlasticoCorte},
      {v:'tacos', l:tr('With cleats or spikes (soccer, athletics), cycling, wrestling or boxing'), off:s=> edadDe(s) === 'bebe' ? SOLO_ADULTO.tacos : null},
      {v:'esqui', l:tr('Ski or snowboard'), off:s=> edadDe(s) === 'bebe' ? SOLO_ADULTO.esqui : null}],
    implica:{tenis:{altura:'bajo'}, bota:{altura:'tobillo'}, botin:{altura:'tobillo'}, esqui:{altura:'tobillo'}, bota_lluvia:{altura:'tobillo', upper:'plastico', sole:'caucho', impermeable:true},
      sandalia:{altura:'bajo'}, slide:{altura:'bajo'}, mocasin:{altura:'bajo'}, pantufla:{altura:'bajo'}, zapato:{altura:'bajo'}, tacon:{altura:'bajo'}, acuatico:{altura:'bajo'},
      zueco:{altura:'bajo', upper:'plastico', sole:'caucho'}, chancla_tetones:{altura:'bajo', upper:'plastico', sole:'caucho', rodeaDedo:true}, danza:{altura:'bajo'}}},
  {id:'altura', label:tr('Height'), tipo:'seg', aplica:s=>s.tipo === 'calzado',
    ops:[{v:'bajo', l:tr('Does not cover the ankle'), off:s=> SI_TOBILLO.includes(s.estiloCalz) ? tr('A boot or ankle boot covers the ankle.') : null},
      {v:'tobillo', l:tr('Covers the ankle'), off:s=> NO_TOBILLO.includes(s.estiloCalz) ? tr('This style does not cover the ankle.') : null},
      {v:'rodilla', l:tr('Also covers the knee'), off:s=> NO_TOBILLO.concat(['botin','tenis','zapato','senderismo','acuatico']).includes(s.estiloCalz) ? tr('This style does not reach the knee.') : null}]},
  {id:'upper', label:tr('Upper material'), ayuda:tr('the one with the largest external surface, excluding reinforcements and trims'), tipo:'seg', aplica:s=>s.tipo === 'calzado', deComp:'corte',
    fijo:s=>{ const pm = predParte(s, 'corte'); return pm ? pm.pred : null; }, fijoMotivo:s=>motComp('corte', s),
    ops:[{v:'textil', l:tr('Textile'), off:s=> s.estiloCalz === 'chancla_tetones' ? tr('With textile or leather straps, choose "Sandal".') : null},
      {v:'cuero', l:tr('Natural leather'), off:s=> s.estiloCalz === 'chancla_tetones' ? tr('With textile or leather straps, choose "Sandal".') : null},
      {v:'plastico', l:tr('Rubber or plastics (includes synthetic leather)')},
      {v:'otro', l:tr('Other'), off:s=> s.estiloCalz === 'chancla_tetones' ? tr('With straps of another material, choose "Sandal".') : null}]},
  {id:'sole', label:tr('Sole material'), ayuda:tr('the one with the largest surface in contact with the ground'), tipo:'seg', aplica:s=>s.tipo === 'calzado', deComp:'suela',
    fijo:s=>{ const pm = predParte(s, 'suela', 'suela'); return pm ? pm.pred : null; }, fijoMotivo:s=>motComp('suela', s, 'suela'),
    ops:[{v:'caucho', l:tr('Rubber or plastics (EVA, PU, TPU)')},
      {v:'cuero', l:tr('Leather'), off:s=> ['chancla_tetones','bota_lluvia','zueco','acuatico'].includes(s.estiloCalz) ? tr('This style has a rubber or plastic sole.') : null},
      {v:'otro', l:tr('Other (wood, cork, textile)'), off:s=> ['chancla_tetones','bota_lluvia','acuatico'].includes(s.estiloCalz) ? tr('This style has a rubber or plastic sole.') : null}]},
  {id:'rodeaDedo', tipo:'check', label:tr('Straps over the instep that go around the big toe'), aplica:s=>s.tipo === 'calzado' && s.estiloCalz === 'sandalia'},
  {id:'disenio', label:tr('Design'), tipo:'seg', aplica:s=>s.tipo === 'calzado' && s.estiloCalz === 'tenis',
    ops:[{v:'entrenamiento', l:tr('Athletic: running, trail running, training, basketball, tennis')}, {v:'casual', l:tr('Casual or lifestyle')}, {v:'skate', l:tr('Skate')}]},
  {id:'puntera', label:tr('Protective toe cap'), tipo:'seg', aplica:s=>s.tipo === 'calzado' && PUNTERA_EST.includes(s.estiloCalz),
    ops:[{v:'ninguna', l:tr('No toe cap'), off:s=> s.estiloCalz === 'seguridad' ? tr('Safety footwear has a toe cap; say whether it is metal or not.') : null},
      {v:'metalica', l:tr('Metal (steel, aluminum)'), off:s=> ['bebe','nino'].includes(edadDe(s)) ? MSG_PUNTERA : null},
      {v:'no_metalica', l:tr('Non-metal (composite)'), off:s=> ['bebe','nino'].includes(edadDe(s)) ? MSG_PUNTERA : null}]},
  {id:'impermeable', tipo:'check', label:tr('Waterproof: upper and sole joined without stitches, rivets, nails or screws (molded or injected)'), aplica:s=>s.tipo === 'calzado',
    offCheck:s=> !(s.upper === 'plastico' && s.sole === 'caucho') ? tr('Only applies if upper and sole are rubber or plastics.') : null},
  {id:'materialCinturon', label:tr('Belt material'), tipo:'seg', aplica:s=>s.tipo === 'cinturon', deComp:'material',
    fijo:s=>matDerivado(s, 'material', {cuero:'cuero', textil:'textil', plastico:'plastico', otro:'otro', metal:'otro'}), fijoMotivo:s=>motComp('material', s),
    ops:[{v:'cuero', l:tr('Leather')}, {v:'textil', l:tr('Textile')}, {v:'plastico', l:tr('Plastic or synthetic leather')}, {v:'otro', l:tr('Other')}]},
  {id:'exterior', label:tr('Outer surface'), tipo:'seg', aplica:s=>grupoTipo(s.tipo) === 'bolso', deComp:'exterior',
    fijo:s=>matDerivado(s, 'exterior', {cuero:'cuero', textil:'textil', plastico:'plastico', otro:'otro'}), fijoMotivo:s=>motComp('exterior', s),
    ops:[{v:'textil', l:tr('Textile')}, {v:'plastico', l:tr('Plastic sheeting')}, {v:'cuero', l:tr('Leather')}, {v:'otro', l:tr('Other')}]},
  {id:'casco', tipo:'check', label:tr('It is a protective helmet (bike, skate, ski, work)'), aplica:s=>s.tipo === 'gorra'},
  {id:'materialGorra', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'gorra' && !s.casco, deComp:'exterior',
    fijo:s=>matDerivado(s, 'exterior', {paja:true, textil:'textil', cuero:'otro', plastico:'otro', otro:'otro'}), fijoMotivo:s=>motComp('exterior', s),
    ops:[{v:'textil', l:tr('Fabric or knit')}, {v:'paja', l:tr('Straw or plaited fibers')}, {v:'otro', l:tr('Other (plastic, leather)')}]},
  {id:'alVacio', tipo:'check', label:tr('Vacuum insulation (thermos)'), aplica:s=>s.tipo === 'botella'},
  {id:'materialBotella', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'botella', deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); if (!c) return null; return c.pred === 'metal' ? (c.aluminio ? 'aluminio' : 'acero') : c.pred === 'plastico' ? 'plastico' : null; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'acero', l:tr('Stainless steel')}, {v:'aluminio', l:tr('Aluminum')}, {v:'plastico', l:tr('Plastic')}]},
  {id:'telescopica', tipo:'check', label:tr('Telescopic (folding) shaft'), aplica:s=>s.tipo === 'sombrilla'},
  {id:'esBase', tipo:'check', label:tr('It is only the footprint or a tent accessory'), aplica:s=>s.tipo === 'tienda'},
  {id:'kitViaje', tipo:'check', label:tr('It is a travel kit or set (several items in a case)'), aplica:s=>s.tipo === 'cuidado_calzado'},
  {id:'tipoAvio', label:tr('What it is'), tipo:'seg', aplica:s=>s.tipo === 'avios',
    ops:[{v:'boton', l:tr('Button or snap')}, {v:'cremallera', l:tr('Zipper')}, {v:'hebilla', l:tr('Buckle or clasp')}, {v:'ojete', l:tr('Eyelet or hook')}, {v:'remache', l:tr('Rivet')}]},
  {id:'forradoTextil', tipo:'check', label:tr('Covered with fabric'), aplica:s=>s.tipo === 'avios' && s.tipoAvio === 'boton'},
  {id:'materialAvio', label:tr('Material'), tipo:'seg', aplica:s=>['avios','correa_reloj','accesorio_pelo'].includes(s.tipo), deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); if (!c) return null; return ({metal:'metal', plastico:'plastico', textil:'textil', cuero:'cuero'})[c.pred] || 'otro'; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'metal', l:tr('Base metal')}, {v:'plastico', l:tr('Plastic or rubber')}, {v:'textil', l:tr('Textile')}, {v:'cuero', l:tr('Leather')}, {v:'otro', l:tr('Other')}]},
  {id:'tipoPelo', label:tr('What it is'), tipo:'seg', aplica:s=>s.tipo === 'accesorio_pelo',
    ops:[{v:'pasador', l:tr('Hair clip, comb or rigid headband')}, {v:'horquilla', l:tr('Hairpin or bobby pin')}, {v:'liga', l:tr('Hair tie, scrunchie or fabric headband')}]},
  {id:'pelNat', label:tr('Fur type'), tipo:'seg', aplica:s=>s.tipo === 'peleteria',
    ops:[{v:'natural', l:tr('Natural fur (hide with hair)')}, {v:'artificial', l:tr('Faux fur')}]},
  {id:'esPrenda', tipo:'check', label:tr('It is a garment or clothing accessory'), aplica:s=>s.tipo === 'peleteria' && s.pelNat === 'natural'},
  {id:'hamacaRed', tipo:'check', label:tr('It is netting (knotted mesh), not fabric'), aplica:s=>s.tipo === 'hamaca'},
  {id:'producto', label:tr('Product'), tipo:'seg', aplica:s=>s.tipo === 'cuidado_calzado',
    ops:[{v:'crema', l:tr('Cream, polish, wax or cleaner')}, {v:'spray', l:tr('Waterproofing or protective spray')}, {v:'cepillo', l:tr('Brush')}]},
  {id:'materialLlavero', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'llavero', deComp:'material',
    fijo:s=>matDerivado(s, 'material', {metal:true, cuero:'cuero', textil:'textil', plastico:'plastico'}), fijoMotivo:s=>motComp('material', s),
    ops:[{v:'metal', l:tr('Metal')}, {v:'cuero', l:tr('Leather')}, {v:'textil', l:tr('Textile (lanyard, webbing)')}, {v:'plastico', l:tr('Plastic or rubber')}]},
  {id:'pantalla', label:tr('Watch type'), tipo:'seg', aplica:s=>s.tipo === 'reloj',
    ops:[{v:'analogico', l:tr('Analog (hands)')}, {v:'digital', l:tr('Digital')}, {v:'combinado', l:tr('Analog and digital')}, {v:'inteligente', l:tr('Smartwatch')}]},
  {id:'presentacion', label:tr('Form'), tipo:'seg', aplica:s=>s.tipo === 'magnesio',
    ops:[{v:'polvo', l:tr('Powder or block')}, {v:'liquido', l:tr('Liquid')}]},
  {id:'tipoColch', label:tr('Type'), tipo:'seg', aplica:s=>s.tipo === 'colchoneta',
    ops:[{v:'inflable', l:tr('Inflatable pad')}, {v:'espuma', l:tr('Foam or self-inflating pad')}, {v:'almohada', l:tr('Pillow or cushion')}]},
  {id:'mueble', label:tr('Furniture'), tipo:'seg', aplica:s=>s.tipo === 'mueble_camping', ops:[{v:'silla', l:tr('Chair or stool')}, {v:'mesa', l:tr('Table')}]},
  {id:'acolchada', tipo:'check', label:tr('Padded seat or backrest (with fill)'), aplica:s=>s.tipo === 'mueble_camping' && s.mueble !== 'mesa'},
  {id:'materialMueble', label:tr('Frame material'), tipo:'seg', aplica:s=>(s.tipo === 'mueble_camping' && s.mueble === 'mesa') || (s.tipo === 'exhibidor' && s.tipoExhib !== 'maniqui'), deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); return c && ['metal','madera','plastico'].includes(c.pred) ? c.pred : null; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'metal', l:tr('Metal')}, {v:'madera', l:tr('Wood')}, {v:'plastico', l:tr('Plastic')}]},
  {id:'rizo', tipo:'check', label:tr('Terry or loop pile (classic towel)'), aplica:s=>s.tipo === 'toalla'},
  {id:'materialBisu', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'bisuteria', deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); return c ? ({metal:'metal', cuero:'cuero', textil:'textil'})[c.pred] || 'otro' : null; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'metal', l:tr('Base metal (steel, brass, zinc)')}, {v:'cuero', l:tr('Leather')}, {v:'textil', l:tr('Textile or cord')}, {v:'otro', l:tr('Plastic, wood or other')}]},
  {id:'tipoParche', label:tr('Type'), tipo:'seg', aplica:s=>s.tipo === 'parche',
    ops:[{v:'sticker', l:tr('Printed sticker or decal')}, {v:'bordado', l:tr('Embroidered patch')}, {v:'tejido', l:tr('Woven patch or badge')}, {v:'pvc', l:tr('PVC or rubber patch')}]},
  {id:'actividad', label:tr('Use'), tipo:'seg', aplica:s=>s.tipo === 'equipo_deporte',
    ops:[{v:'fitness', l:tr('Exercise or gym (yoga mat, bands, jump rope)')}, {v:'escalada', l:tr('Climbing (crash pad, holds)')}, {v:'protecciones', l:tr('Protective pads (knee, elbow)')}, {v:'pelota', l:tr('Inflatable ball')}, {v:'otro', l:tr('Other sports equipment')}]},
  {id:'baseAncha', tipo:'check', label:tr('The base is 40 cm wide or more'), aplica:s=>s.tipo === 'bolsa_compra' && s.materialBolsa === 'papel'},
  {id:'materialBolsa', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'bolsa_compra', deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); return c ? ({papel:'papel', textil:'tela', plastico:'plastico'})[c.pred] || null : null; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'papel', l:tr('Paper or card stock')}, {v:'plastico', l:tr('Plastic')}, {v:'tela', l:tr('Fabric or non-woven, reusable with handles')}]},
  {id:'materialCaja', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'caja', deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); if (!c) return null; if (c.pred === 'papel') return c.corrugado ? 'corrugado' : 'plegadizo'; return c.pred === 'plastico' ? 'plastico' : null; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'corrugado', l:tr('Corrugated cardboard')}, {v:'plegadizo', l:tr('Card stock or non-corrugated board (shoe box)')}, {v:'plastico', l:tr('Plastic')}]},
  {id:'materialGancho', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'gancho', deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); return c && ['plastico','metal','madera'].includes(c.pred) ? c.pred : null; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'plastico', l:tr('Plastic')}, {v:'metal', l:tr('Wire or metal')}, {v:'madera', l:tr('Wood')}]},
  {id:'materialEtiqueta', label:tr('Material'), tipo:'seg', aplica:s=>s.tipo === 'etiqueta', deComp:'material',
    fijo:s=>{ const c = claseMat(s, 'material'); return c ? ({papel:'papel', textil:'tejida', plastico:'plastico'})[c.pred] || null : null; }, fijoMotivo:s=>motComp('material', s),
    ops:[{v:'papel', l:tr('Printed paper or board (hang tag)')}, {v:'tejida', l:tr('Woven (neck label)')}, {v:'plastico', l:tr('Plastic or PVC')}]},
  {id:'tipoExhib', label:tr('Type'), tipo:'seg', aplica:s=>s.tipo === 'exhibidor',
    ops:[{v:'mueble', l:tr('Fixture, gondola or display')}, {v:'maniqui', l:tr('Mannequin or bust')}]},
  {id:'parteSkate', label:tr('Form'), tipo:'seg', aplica:s=>s.tipo === 'patineta', info:true, soloNac:true,
    ops:[{v:'completa', l:tr('Complete skateboard')}, {v:'tabla', l:tr('Deck only')}, {v:'partes', l:tr('Wheels, trucks or other parts')}]}
];
const ATTR_IDS = ATTRS.map(a=>a.id);
const ATTR_BY = {}; ATTRS.forEach(a=>{ ATTR_BY[a.id] = a; });
function opcionLbl(id, v){ const a = ATTR_BY[id]; if (!a) return String(v); if (a.tipo === 'check') return v ? tr('Yes') : tr('No'); const o = (a.ops||[]).find(x=>x.v === v); return o ? o.l : String(v); }
function prepararEstado(s){
  s._matGuante = '';
  if (s.tipo === 'guantes'){ const c = parseComp((s.comp||{}).exterior || ''); if (c && c.pred && c.pred.grupo === 'cuero') s._matGuante = 'cuero'; }
  return s;
}
function normalizar(s){
  prepararEstado(s);
  const avisos = [];
  for (let k = 0; k < 3; k++){
    for (const a of ATTRS){
      if (!a.aplica(s)) continue;
      const fx = a.fijo ? a.fijo(s) : null;
      if (fx != null && s[a.id] !== fx){
        if (s[a.id] && a.deComp) avisos.push(tr('{0}: changed from "{1}" to "{2}". {3}', [a.label, opcionLbl(a.id, s[a.id]), opcionLbl(a.id, fx), typeof a.fijoMotivo === 'function' ? a.fijoMotivo(s) : '']));
        s[a.id] = fx;
      }
      const v = s[a.id];
      if (a.tipo === 'check'){
        const r = v && a.offCheck ? a.offCheck(s) : null;
        if (r){ s[a.id] = false; avisos.push(tr('Unchecked "{0}": {1}', [a.label, r])); }
      } else if (v){
        const op = a.ops.find(o=>o.v === v);
        const r = !op ? tr('invalid option') : (op.off ? op.off(s) : null);
        if (r){ s[a.id] = ''; avisos.push(tr('Removed "{0}": {1}', [op ? op.l : v, r])); }
      }
    }
  }
  for (const a of ATTRS){
    if (a.def && a.aplica(s) && !s[a.id]){ s[a.id] = a.def; continue; }
    if (a.tipo === 'check' || a.info || !a.aplica(s) || s[a.id]) continue;
    const validas = a.ops.filter(o=>!(o.off && o.off(s)));
    if (validas.length === 1) s[a.id] = validas[0].v;
  }
  return [...new Set(avisos)];
}
function opcionesValidas(a, s){ const fx = a.fijo ? a.fijo(s) : null; return (a.ops || []).filter(o=>(fx == null || o.v === fx) && !(o.off && o.off(s))); }
function aplicarImplica(s, id, v){
  const a = ATTR_BY[id];
  const patch = a && a.implica && a.implica[v];
  if (!patch) return [];
  const cambiados = [];
  for (const [k,val] of Object.entries(patch)){
    const opt = ATTR_BY[k];
    const actual = s[k];
    let invalido = false;
    if (opt && opt.tipo !== 'check' && actual){ const op = opt.ops.find(o=>o.v === actual); invalido = !op || !!(op.off && op.off(s)); }
    if (actual && !invalido) continue;
    if (opt && opt.tipo !== 'check'){ const op = opt.ops.find(o=>o.v === val); if (op && op.off && op.off(Object.assign({}, s, {[k]:val}))) continue; }
    if (s[k] !== val){ s[k] = val; cambiados.push(k); }
  }
  return cambiados;
}
function atributosLegibles(s){
  const out = [];
  for (const a of ATTRS){
    if (!a.aplica(prepararEstado(Object.assign({}, s)))) continue;
    const v = s[a.id];
    if (a.tipo === 'check'){ if (v) out.push([a.label.split(':')[0].split('(')[0].trim(), tr('Yes')]); }
    else if (v) out.push([a.label, opcionLbl(a.id, v)]);
  }
  return out;
}

/* ---------- Detección desde texto ---------- */
const DET_TIPO = [
  ['caja', /\b(shoe ?box(es)?|cajas? (de|para) (zapatos|calzado|carton)|carton box|corrugated box|cajas?|cartones?)\b/],
  ['bolsa_compra', /\b(shopping bags?|paper bags?|gift bags?|bolsas? (de|para) (compras?|papel|tienda|regalo)|bolsas? reutilizables?)\b/],
  ['gancho', /\b(hangers?|ganchos? para ropa|perchas?|colgador(es)?)\b/],
  ['etiqueta', /\b(hang ?tags?|labels?|etiquetas?|price tags?)\b/],
  ['exhibidor', /\b(displays?|exhibidor(es)?|mannequins?|maniqui(es)?|bustos?|gondolas?|shoe wall)\b/],
  ['mascota', /\b(dogs?|perros?|mascotas?|pets?|leash|correas? para perro|collar para perro|dog harness|arnes para perro)\b/],
  ['saco', /\b(sleeping ?bags?|saco de dormir|bolsa de dormir)\b/],
  ['colchoneta', /\b(sleeping ?pads?|colchonetas? inflables?|air ?mattress|colchon inflable|camping mat|sleep ?mat|pillows?|almohadas?|cojin(es)?|cushions?)\b/],
  ['tienda', /\b(tents?|tienda de campana|carpa)\b/],
  ['bolso_viaje', /\b(chalk ?bags?|chalk ?buckets?|bolsas? (de|para) magnesio|bolsitas? (de|para) magnesio)\b/],
  ['magnesio', /\b(chalk|magnesio|tiza para escalar)\b/],
  ['equipo_deporte', /\b(crash ?pads?|boulder(ing)? pads?|yoga mats?|mats? de yoga|resistance bands?|bandas? de resistencia|ligas de ejercicio|jump ropes?|cuerdas? (de|para) saltar|knee pads?|rodilleras?|coderas?|elbow pads?|wrist guards?|munequeras?|pelotas?|balon(es)?|footballs?|basketballs?)\b/],
  ['linterna', /\b(headlamps?|flashlights?|linternas?|lamparas? frontal(es)?|lanterns?|farol(es)?)\b/],
  ['toalla', /\b(towels?|toallas?)\b/],
  ['manta', /\b(blankets?|mantas?|frazadas?|cobijas?|throw)\b/],
  ['mueble_camping', /\b(camp ?chairs?|camp ?tables?|folding (chair|table)s?|chairs?|sillas?|mesas? plegables?|taburete|stool)\b/],
  ['parche', /\b(stickers?|calcomanias?|patch(es)?|parches?|decals?)\b/],
  ['cuidado_calzado', /\b(shoe ?care|betun|crema para (zapatos|calzado)|shoe ?cleaner|cleaning kit|kit de limpieza|protector spray|impermeabilizante|shoe polish|polish|cepillo|brush|desodorante para (zapatos|calzado)|repelente)\b/],
  ['plantilla', /\b(insoles?|plantillas?|taloneras?|heel (cushions?|grips?)|footbeds?)\b/],
  ['cordones', /\b(laces|shoelaces?|cordones|agujetas|pasadores)\b/],
  ['polainas', /\b(leg gaiters?|trail gaiters?|hiking gaiters?|polainas?|gaiters? para (botas|calzado))\b/],
  ['llavero', /\b(keychains?|key ?chains?|key ?rings?|llaveros?|lanyards?)\b/],
  ['bisuteria', /\b(bracelets?|pulseras?|necklaces?|collares?|earrings?|aretes|pins?|pines|anillos?|charms?)\b/],
  ['correa_reloj', /\b(watch ?(band|strap)s?|correas? de reloj|pulseras? de reloj)\b/],
  ['reloj', /\b(watch(es)?|smartwatch|relojes|reloj)\b/],
  ['bolso_viaje', /\b(belt ?bag|duffel|duffle|base camp|waist ?packs?|lumbar|fanny|cangurera|rinonera|hip ?packs?|neceser|toiletry|dopp|gym bag|sling|lunch ?(bag|box)|lonchera|cooler bag|hydration pack|pencil case|cosmetiquera|cosmetic bag|shoe bag|bolsa para zapatos)\b/],
  ['mochila', /\b(backpacks?|mochilas?|daypacks?|rucksacks?|borealis|jester|recon|router|hot shot|surge|vault)\b/],
  ['billetera', /\b(wallets?|billeteras?|monederos?|card ?holder|tarjetero|estuche|glasses case|phone case|funda de celular|porta ?pasaporte)\b/],
  ['maleta', /\b(luggage|trolley|roller|rolling thunder|maletas?|suitcases?|briefcase|maletin|laptop (sleeve|case|bag)|funda de laptop|portafolio)\b/],
  ['bolso_mano', /\b(totes?|crossbody|cross body|handbags?|shoulder bags?|bolsos?|purses?|carteras? de mano)\b/],
  ['lentes_sol', /\b(sunglasses|lentes de sol|gafas de sol|anteojos de sol|lentes oscuros)\b/],
  ['sombrilla', /\b(umbrellas?|paraguas|sombrillas?)\b/],
  ['botella', /\b(bottles?|botellas?|termos?|thermos|tumblers?|vaso termico|flask|pachon(es)?|cantimplora|hydro flask)\b/],
  ['patineta', /\b(skateboards?|patinetas?|skate ?decks?|decks?|cruiser board|complete skate|skate wheels|ruedas de skate|trucks?)\b/],
  ['bastones', /\b(trekking poles?|bastones|hiking poles?)\b/],
  ['calzado', /\b(shoes?|sneakers?|zapatos?|zapatillas?|tenis|boots?|botas?|botin(es)?|sandals?|sandalias?|slides?|chanclas?|flip ?flops?|mules?|clogs?|zuecos?|slip-?on|loafers?|mocasin(es)?|moccasins?|moc|slippers?|pantuflas?|heels?|tacon(es)?|stilettos?|pumps|flats|balerinas?|footwear|calzado|old skool|sk8|authentic|ultrarange|knu skool|half cab|chukka|vectiv|hedgehog|chilkat|moab|second shift|steel toe|safety toe|work boot|water shoes?|overshoes?|cubrecalzados?|galoshes?|dance shoes?|zapatillas de baile|house shoes?)\b/],
  ['calcetines', /\b(socks?|calcetin|calcetines|calcetas?|tines)\b/],
  ['guantes', /\b(gloves?|guantes?|mitts?|mittens?)\b/],
  ['cinturon', /\b(belts?|cinturon(es)?|cincho|faja)\b/],
  ['gorra', /\b(caps?|hats?|beanies?|gorras?|gorros?|sombreros?|bucket|trucker|visor|balaclava|pasamontanas|helmets?|casco)\b/],
  ['traje_bano', /\b(swim|swimsuit|swimwear|bikini|board ?shorts?|boardshorts|traje de bano|vestido de bano|banador|pantaloneta de bano)\b/],
  ['brasier', /\b(bra|bras|brasier|sosten|sujetador|sports bra|bralette)\b/],
  ['ropa_interior', /\b(boxers?|boxer briefs?|briefs?|underwear|calzoncillos?|bragas?|panties|calzon(es)?|ropa interior|pajamas?|pyjamas?|pijamas?|sleepwear|camison|undershirt|camiseta interior|robes?|bathrobe|albornoz)\b/],
  ['enterizo', /\b(coveralls?|jumpsuits?|rompers?|onesies?|monos?|mamelucos?|enterizos?|overol completo|boiler ?suit|bodysuits?|pañaleros?|panaleros?)\b/],
  ['conjunto', /\b(tracksuits?|conjunto deportivo|sweatsuit|jogging set|ski suit|snowsuit|traje de esqui)\b/],
  ['vestido', /\b(dress|dresses|vestidos?)\b/],
  ['falda', /\b(skirts?|skort|faldas?)\b/],
  ['chaqueta', /\b(jackets?|jkt|chaquetas?|chamarras?|chumpas?|parkas?|anoraks?|vests?|chalecos?|gilet|windbreakers?|rompevientos|puffer|nuptse|thermoball|antora|softshell|hardshell|insulated|impermeable|ponchos?|capa de lluvia|blazers?|sport ?coat|saco de vestir)\b/],
  ['camiseta', /\b(tees?|t-?shirts?|camisetas?|playeras?|tanks?|singlets?|base ?layer)\b/],
  ['sudadera', /\b(hoodies?|hoody|hooded|sweatshirts?|sudaderas?|crews?|crewneck|pullovers?|sweaters?|sueteres?|cardigans?|fleece|polar|1\/4 ?zip|quarter ?zip|denali|glacier)\b/],
  ['camisa', /\b(shirts?|camisas?|polos?|blouses?|blusas?|flannel|button ?down|button ?up)\b/],
  ['pantalon', /\b(pants?|pantalon|pantalones|shorts?|joggers?|trousers?|jeans?|leggings?|tights|cargo|chinos?|capri|overol(es)?|overalls?|bib)\b/],
  ['bufanda', /\b(scarf|scarves|bufandas?|gaiters?|neck ?gaiter|neckwarmer|buff|bandanas?|panuelos?)\b/],
  ['bolso_viaje', /\b(bags?|bolsas?|bolsitas?|pouch(es)?)\b/],
  ['accesorio_pelo', /\b(scrunchies?|hair ?(clip|tie|band)s?|headbands?|diademas?|pasadores? para (el )?pelo|horquillas?|bobby pins?|peinetas?|pinzas? para (el )?pelo)\b/],
  ['avios', /\b(zippers?|cremalleras?|botones|buttons|hebillas?|buckles?|ojetes?|eyelets?|remaches?|rivets?|snaps?|zipper pulls?)\b/],
  ['hamaca', /\b(hammocks?|hamacas?|chinchorros?)\b/],
  ['peleteria', /\b(faux fur|fur (throw|scarf|stole)|peleteria|piel sintetica)\b/]
];
const DET_ESTILO = [
  ['seguridad', /\b(safety|seguridad|industrial|steel toe|composite toe|punta de acero|puntera de acero|puntera metalica|punta de composite|work shoes?|zapato de trabajo|dieléctric[oa]|electrical hazard)\b/],
  ['bota_lluvia', /\b(rain ?boots?|bota de lluvia|botas de hule|wellingtons?)\b/],
  ['esqui', /\b(ski boots?|snowboard boots?|botas? de esqui|botas? de snowboard)\b/],
  ['roller', /\b(roller|heelys|con ruedas|with wheels|patin(es)?)\b/],
  ['tenis', /\b(indoors?|futsal|futbol sala|futbol rapido|turf)\b/],
  ['tacos', /\b(cleats?|spikes?|tacos|tachones|cycling shoes?|ciclismo|boxing|wrestling)\b/],
  ['zueco', /\b(clogs?|zuecos?|hydro moc)\b/],
  ['acuatico', /\b(water shoes?|aqua shoes?|acuatic[oa]s?|hydro)\b/],
  ['botin', /\b(botin(es)?|chelsea|chukka|ankle boots?|desert boots?|safari)\b/],
  ['bota', /\b(boots?|botas?)\b/],
  ['senderismo', /\b(hiking|hiker|senderismo|trekking|moab|hedgehog|approach)\b/],
  ['chancla_tetones', /\b(flip ?flops?|chanclas? de dedo|thong sandals?|sandalias de playa|chinelas? con espigas)\b/],
  ['sandalia', /\b(sandals?|sandalias?|sandalia flat|anklestrap|pata de gallo)\b/],
  ['slide', /\b(slides?|chanclas?)\b/],
  ['pantufla', /\b(slippers?|pantuflas?|house shoes?|calzado de casa)\b/],
  ['danza', /\b(dance shoes?|danza|ballet|jazz shoes?|zapatillas de baile)\b/],
  ['cubrecalzado', /\b(overshoes?|cubrecalzados?|cubre ?calzado|galoshes?)\b/],
  ['mocasin', /\b(mocasin(es)?|loafers?|moccasins?|moc|boat shoes?|boatshoes?|nautico|drivers?)\b/],
  ['tacon', /\b(tacon(es)?|heels?|stilettos?|pumps|cunas?|wedges?)\b/],
  ['zapato', /\b(zapatos?|dress shoes?|oxfords?|derby|blucher|brogues?|monk ?straps?|wing ?tips?|flats|balerinas?|ballerinas?|escolar|alpargatas?|espadrilles?|mules?)\b/],
  ['tenis', /\b(sneakers?|tenis|trainers?|running|shoes?|old skool|sk8|authentic|era|slip-?on|ultrarange|knu skool|half cab|vectiv)\b/]
];
function parseGenero(t){
  const s = norm(t).trim();
  if (!s) return '';
  if (/^(w|wm|wmn|wmns|f)\b/.test(s) || /\b(womens?|mujer(es)?|damas?|ladies|girls?|nina|ninas|female|femenino)\b/.test(s)) return 'F';
  if (/^(m|mn|mns)\b/.test(s) || /\b(mens?|hombres?|caballeros?|boys?|nino|ninos|male|masculino)\b/.test(s)) return 'M';
  if (/^(u|ua|uy)\b/.test(s) || /\b(unisex)\b/.test(s)) return 'U';
  return '';
}
function parseEdad(t){
  const s = norm(t);
  if (/\b(baby|bebe|infant|newborn|recien nacido|onesies?|mameluco|panalero)\b/.test(s)) return 'bebe';
  if (/\b(kids?|youth|junior|jr|nino|nina|ninos|ninas|infantil|toddler|td|ps|gs|boys?|girls?|juvenil)\b/.test(s)) return 'nino';
  return '';
}
function parseTallas(t){
  const s = norm(t);
  if (!s.trim()) return '';
  if (/\b(nb|newborn|recien nacido|\d{1,2}\s*-\s*\d{1,2}\s*(m|meses)|\d{1,2}\s*(m|meses)|0-3|3-6|6-9|6-12|12-18|18-24)\b/.test(s)) return 'bebe';
  if (/\b([2-7]t|youth|kids|junior|jr|\d{1,2}\s*(y|yrs|anos)|toddler|xs\/s kids)\b/.test(s)) return 'nino';
  if (/\b(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl)\b/.test(s)) return 'adulto';
  return '';
}
function detectar(texto, comp, tallas, tipoForzado){
  const s = norm(texto), compTxt = norm(Object.values(comp || {}).join(' ')), both = s + ' ' + compTxt;
  const d = {};
  if (tipoForzado) d.tipo = tipoForzado;
  else for (const [t,re] of DET_TIPO){ if (re.test(s)){ d.tipo = t; break; } }
  const g = parseGenero(s); if (g) d.genero = g;
  const e = parseEdad(s) || parseTallas(tallas || ''); if (e === 'bebe') d.edad = 'bebe'; else if (e === 'nino') d.edadNac = 'nino';
  if (/\b(fleece|polar|denali|glacier|knit|knitted|punto|jersey|pique|terry|waffle|polos?|hoodies?|sweatshirts?|leggings?|onesies?)\b/.test(both)) d.tejido = 'punto';
  else if (/\b(board ?shorts?|boardshorts|swim trunks|woven|plano|denim|jeans?|flannel|franela|poplin|popelina|canvas|lona|ripstop|twill|sarga|taslan|oxford|chambray|corduroy|pana|puffer|down|nuptse|thermoball|insulated|parkas?|anoraks?|windbreakers?|rompevientos|cargo|chinos?|coveralls?|boiler ?suit)\b/.test(both)) d.tejido = 'plano';
  if (/\b(dryvent|dry vent|gore-?tex|futurelight|waterproof|laminad[oa]s?|laminated|pu coated|coated|recubiert[oa]s?|hyvent|hardshell|rain ?jacket|rain ?shell)\b/.test(both)) d.recubierta = true;
  if (/\b(down|plumon|pluma|goose|duck|700 fill|600 fill|550 fill)\b/.test(both)) d.relleno_tipo = 'plumon';
  else if (/\b(thermoball|primaloft|heatseeker|synthetic insulation|relleno sintetico|insulated)\b/.test(both)) d.relleno_tipo = 'sintetico';
  if (d.tipo === 'chaqueta'){
    if (/\b(reflectiv[oa]|hi-?vis|alta visibilidad|safety vest|chaleco de seguridad)\b/.test(s)) d.hechura = 'reflectivo';
    else if (/\b(blazers?|sport ?coat|saco de vestir|americana)\b/.test(s)) d.hechura = 'blazer';
    else if (/\b(vests?|chalecos?|gilet)\b/.test(s)) d.hechura = /\b(down|puffer|insulated|acolchad[oa]|relleno|thermoball|nuptse|padded|plumon)\b/.test(both) ? 'chaleco_relleno' : (/\b(fleece|polar|knit|softshell)\b/.test(both) ? 'chaleco' : '');
    else d.hechura = 'chaqueta';
    if (!d.hechura) delete d.hechura;
  }
  if (d.tipo === 'sudadera'){
    if (/\b(full ?zip|fz|cierre completo|zip ?up|zip hoodie)\b/.test(s)) d.hechuraSud = 'cierre';
    else if (/\b(pullover|po|crew|crewneck|1\/4 ?zip|quarter ?zip|half ?zip)\b/.test(s)) d.hechuraSud = 'pullover';
  }
  if (d.tipo === 'ropa_interior'){
    if (/\b(robes?|bata|albornoz|bathrobe)\b/.test(s)) d.prendaInt = 'bata';
    else if (/\b(pajamas?|pyjamas?|pijamas?|sleepwear|camison|nightgown)\b/.test(s)) d.prendaInt = 'pijama';
    else if (/\b(undershirt|camiseta interior)\b/.test(s)) d.prendaInt = 'camiseta_int';
    else d.prendaInt = 'interior';
  }
  if (d.tipo === 'bufanda'){ d.tipoBufanda = /\b(bandanas?|panuelos?|handkerchief)\b/.test(s) ? 'bandana' : 'bufanda'; if (d.tipoBufanda === 'bandana' && !d.tejido) d.tejido = 'plano'; }
  if (d.tipo === 'camiseta' && /\b(polo|henley con cuello)\b/.test(s)) d.polo = true;
  const tipoCalz = d.tipo === 'calzado';
  if (tipoCalz){
    for (const [st,re] of DET_ESTILO){ if (re.test(s)){ d.estiloCalz = st; break; } }
    if (/\b(hi|high|high-?top|mid|boots?|botas?|botin(es)?|chukka|mte)\b/.test(s)) d.altura = 'tobillo';
    if (/\b(running|run|trail|training|trainers?|basketball|baloncesto|gym|gimnasia|entrenamiento|vectiv|deportivo)\b/.test(s)) d.disenio = 'entrenamiento';
    else if (/\b(skate|pro|skateboarding)\b/.test(s)) d.disenio = 'skate';
    else if (d.estiloCalz === 'tenis' || !d.estiloCalz){ d.disenio = 'casual'; d._def = ['disenio']; }
    if (/\b(steel toe|punta de acero|acero|aluminum toe|alloy toe|puntera metalica)\b/.test(s)) d.puntera = 'metalica';
    else if (/\b(composite|nano toe|carbon toe|punta de composite)\b/.test(s)) d.puntera = 'no_metalica';
    if (!d.estiloCalz){ d.estiloCalz = 'tenis'; d._def = (d._def || []).concat(['estiloCalz']); }
    const corte = parseMat((comp||{}).corte || '', 'corte');
    if (corte && corte.pred) d.upper = corte.pred;
    else {
      const upCuero = /\b(leather|cuero|suede|gamuza|nubuck|piel|charol)\b/.test(both) && !/\b(sintetic[oa]|synthetic|faux|vegan|pu leather)\b/.test(both);
      const upTextil = /\b(canvas|lona|mesh|malla|knit|textile|textil|nylon|ripstop|corduroy|pana|poliester|polyester)\b/.test(both);
      const upPlast = /\b(pvc|eva|rubber upper|plastic|plastico|hule|sintetic[oa]|synthetic|faux leather|pu leather)\b/.test(both);
      if (upCuero && upTextil) d.upperMixto = true;
      else if (upCuero) d.upper = 'cuero';
      else if (upTextil) d.upper = 'textil';
      else if (upPlast) d.upper = 'plastico';
    }
    const suela = parseMat((comp||{}).suela || '', 'suela');
    if (suela && suela.pred) d.sole = suela.pred;
    else if (/\b(leather sole|suela de cuero)\b/.test(both)) d.sole = 'cuero';
    const imp = ATTR_BY.estiloCalz.implica[d.estiloCalz] || {};
    for (const [k,v] of Object.entries(imp)) if (d[k] === undefined){ d[k] = v; d._def = (d._def || []).concat([k]); }
    if (/\b(toe ?loop|toe ?post|rodea el dedo|entre dedo|thong)\b/.test(s)) d.rodeaDedo = true;
  }
  if (/\b(leather|cuero)\b/.test(both) && !/\b(sintetic[oa]|synthetic|faux|vegan)\b/.test(both)) d.exterior = 'cuero';
  else if (/\b(nylon|polyester|poliester|canvas|lona|textil|textile|ripstop|cordura)\b/.test(both)) d.exterior = 'textil';
  else if (/\b(pvc|tpu|plastic|plastico)\b/.test(both)) d.exterior = 'plastico';
  if (d.tipo === 'cinturon'){
    if (/\b(leather|cuero)\b/.test(both) && !/\b(sintetic|synthetic|faux)\b/.test(both)) d.materialCinturon = 'cuero';
    else if (/\b(web|webbing|canvas|lona|nylon|poliester|polyester|textil|elastic|elastico|tejido)\b/.test(both)) d.materialCinturon = 'textil';
    else if (/\b(pu|pvc|plastic|plastico|sintetic[oa]|synthetic)\b/.test(both)) d.materialCinturon = 'plastico';
  }
  if (/\b(helmet|casco)\b/.test(s)) d.casco = true;
  if (d.tipo === 'gorra' && /\b(straw|paja|palma)\b/.test(both)) d.materialGorra = 'paja';
  if (d.tipo === 'botella'){
    if (/\b(vacuum|al vacio|termo|thermos|insulated|termico)\b/.test(both)) d.alVacio = true;
    if (/\b(stainless|acero)\b/.test(both)) d.materialBotella = 'acero';
    else if (/\b(aluminio|aluminum)\b/.test(both)) d.materialBotella = 'aluminio';
    else if (/\b(plastic|plastico|tritan|bpa)\b/.test(both)) d.materialBotella = 'plastico';
  }
  if (/\b(telescopic|telescopica|plegable|compact|folding)\b/.test(s)) d.telescopica = true;
  if (d.tipo === 'avios'){
    if (/\b(zippers?|cremalleras?|zipper pulls?)\b/.test(s)) d.tipoAvio = 'cremallera';
    else if (/\b(hebillas?|buckles?)\b/.test(s)) d.tipoAvio = 'hebilla';
    else if (/\b(ojetes?|eyelets?)\b/.test(s)) d.tipoAvio = 'ojete';
    else if (/\b(remaches?|rivets?)\b/.test(s)) d.tipoAvio = 'remache';
    else if (/\b(botones|buttons?|snaps?|broches?)\b/.test(s)) d.tipoAvio = 'boton';
  }
  if (d.tipo === 'accesorio_pelo'){
    if (/\b(scrunchies?|hair ?ties?|ligas?)\b/.test(s) || (/\b(headbands?|diademas?|bandas?)\b/.test(s) && !/\b(plastic|plastico|metal|rigid|rigida)\b/.test(s))) d.tipoPelo = 'liga';
    else if (/\b(horquillas?|bobby pins?)\b/.test(s)) d.tipoPelo = 'horquilla';
    else d.tipoPelo = 'pasador';
  }
  if (d.tipo === 'tienda' && /\b(footprint|base de tienda|base para tienda)\b/.test(s)) d.esBase = true;
  if (d.tipo === 'bolsa_compra' && /\b(base (superior|mayor) a 40|40 ?cm)\b/.test(s)) d.baseAncha = true;
  if (d.tipo === 'peleteria' && /\b(faux|sintetic|artificial|peluche)\b/.test(s)) d.pelNat = 'artificial';
  if (d.tipo === 'cuidado_calzado' && /\b(kit|set|juego|travel|estuche)\b/.test(s)) d.kitViaje = true;
  if (d.tipo === 'cuidado_calzado'){
    if (/\b(spray|protector|impermeabilizante|repelente)\b/.test(s)) d.producto = 'spray';
    else if (/\b(cepillo|brush)\b/.test(s)) d.producto = 'cepillo';
    else d.producto = 'crema';
  }
  if (d.tipo === 'llavero'){
    if (/\b(lanyards?|webbing|cinta|textil|nylon|poliester|polyester)\b/.test(both)) d.materialLlavero = 'textil';
    else if (/\b(leather|cuero)\b/.test(both)) d.materialLlavero = 'cuero';
    else if (/\b(metal|metalic[oa]|zinc|acero|steel|aluminio|aluminum|bronce|brass)\b/.test(both)) d.materialLlavero = 'metal';
    else if (/\b(pvc|plastic|plastico|silicona|silicone|caucho|rubber)\b/.test(both)) d.materialLlavero = 'plastico';
  }
  if (d.tipo === 'reloj'){
    if (/\b(smart|inteligente|gps|bluetooth)\b/.test(s)) d.pantalla = 'inteligente';
    else if (/\b(ana-?digi|anadigi|analogico digital|combinado)\b/.test(s)) d.pantalla = 'combinado';
    else if (/\b(digital)\b/.test(s)) d.pantalla = 'digital';
    else if (/\b(analog|analogico|agujas)\b/.test(s)) d.pantalla = 'analogico';
  }
  if (d.tipo === 'equipo_deporte'){
    if (/\b(crash ?pads?|boulder)/.test(s)) d.actividad = 'escalada';
    else if (/\b(yoga|resistance|resistencia|ligas|jump|saltar|fitness|gym)\b/.test(s)) d.actividad = 'fitness';
    else if (/\b(knee|rodilleras?|coderas?|elbow|wrist|munequeras?|pads?)\b/.test(s)) d.actividad = 'protecciones';
    else if (/\b(pelotas?|balon(es)?|balls?)\b/.test(s)) d.actividad = 'pelota';
  }
  if (d.tipo === 'colchoneta' && /\b(pillows?|almohadas?|cojin(es)?|cushions?)\b/.test(s)) d.tipoColch = 'almohada';
  if (d.tipo === 'mueble_camping') d.mueble = /\b(tables?|mesas?)\b/.test(s) ? 'mesa' : 'silla';
  if (d.tipo === 'toalla' && /\b(terry|rizo|felpa)\b/.test(both)) d.rizo = true;
  if (d.tipo === 'parche'){ if (/\b(stickers?|calcomanias?|decals?)\b/.test(s)) d.tipoParche = 'sticker'; else if (/\b(embroider|bordad)/.test(s)) d.tipoParche = 'bordado'; else if (/\b(woven|tejid)/.test(s)) d.tipoParche = 'tejido'; else if (/\b(pvc|rubber|goma)\b/.test(s)) d.tipoParche = 'pvc'; }
  if (d.tipo === 'bisuteria'){ if (/\b(leather|cuero)\b/.test(both)) d.materialBisu = 'cuero'; else if (/\b(cord|cordon|hilo|textil|woven|tejid)/.test(both)) d.materialBisu = 'textil'; else if (/\b(metal|acero|steel|brass|laton|zinc|enamel|esmalte)/.test(both)) d.materialBisu = 'metal'; }
  if (d.tipo === 'bolsa_compra'){ if (/\b(paper|papel|kraft)\b/.test(both)) d.materialBolsa = 'papel'; else if (/\b(plastic|plastico|polietileno|pe|ldpe|hdpe)\b/.test(both)) d.materialBolsa = 'plastico'; else if (/\b(reutilizable|reusable|tela|non ?woven|no tejid|canvas|lona|algodon|cotton)/.test(both)) d.materialBolsa = 'tela'; }
  if (d.tipo === 'caja'){ if (/\b(corrugad|corrugated)/.test(both)) d.materialCaja = 'corrugado'; else if (/\b(shoe ?box|zapatos|calzado|cartulina|folding)/.test(both)) d.materialCaja = 'plegadizo'; else if (/\b(plastic|plastico)\b/.test(both)) d.materialCaja = 'plastico'; }
  if (d.tipo === 'gancho'){ if (/\b(wood|madera)\b/.test(both)) d.materialGancho = 'madera'; else if (/\b(wire|alambre|metal)\b/.test(both)) d.materialGancho = 'metal'; else if (/\b(plastic|plastico)\b/.test(both)) d.materialGancho = 'plastico'; }
  if (d.tipo === 'etiqueta'){ if (/\b(woven|tejid)/.test(both)) d.materialEtiqueta = 'tejida'; else if (/\b(hang ?tags?|papel|paper|carton|price)/.test(both)) d.materialEtiqueta = 'papel'; else if (/\b(pvc|plastic|plastico)\b/.test(both)) d.materialEtiqueta = 'plastico'; }
  if (d.tipo === 'exhibidor'){ d.tipoExhib = /\b(mannequins?|maniqui(es)?|bustos?)\b/.test(s) ? 'maniqui' : 'mueble'; if (d.tipoExhib === 'mueble'){ if (/\b(metal|steel|acero)\b/.test(both)) d.materialMueble = 'metal'; else if (/\b(wood|madera|mdf)\b/.test(both)) d.materialMueble = 'madera'; else if (/\b(acrylic|acrilico|plastic|plastico)\b/.test(both)) d.materialMueble = 'plastico'; } }
  if (d.tipo === 'magnesio') d.presentacion = /\b(liquid|liquido)\b/.test(s) ? 'liquido' : 'polvo';
  if (d.tipo === 'colchoneta'){
    if (/\b(self-?inflating|autoinflable|foam|espuma)\b/.test(s)) d.tipoColch = 'espuma';
    else if (/\b(inflatable|inflable|air)\b/.test(s)) d.tipoColch = 'inflable';
  }
  if (d.tipo === 'mueble_camping' && /\b(padded|acolchad[oa]|cushion|relleno)\b/.test(s)) d.acolchada = true;
  if (d.tipo === 'patineta'){
    if (/\b(complete|completa)\b/.test(s)) d.parteSkate = 'completa';
    else if (/\b(deck|tabla)\b/.test(s)) d.parteSkate = 'tabla';
    else if (/\b(wheels?|ruedas|trucks?|bearings?|rodamientos)\b/.test(s)) d.parteSkate = 'partes';
  }
  return d;
}
function palabraDe(texto, palabras, marca){
  if (!palabras || !palabras.length) return null;
  const s = ' ' + norm(texto).replace(/[^a-z0-9]+/g, ' ').trim() + ' ';
  const hits = palabras.filter(p=>{
    if (!p || !p.frase || !p.tipo) return false;
    if (p.marca && norm(p.marca).trim() !== norm(marca || '').trim()) return false;
    const f = norm(p.frase).replace(/[^a-z0-9]+/g, ' ').trim();
    return f && s.includes(' ' + f + ' ');
  }).sort((a,b)=>b.frase.length - a.frase.length);
  return hits[0] || null;
}
const PALABRA_ATTRS = ['estiloCalz','altura','disenio','tejido','genero','hechura'];
/* El producto se reconoce por su Estilo (nombre), no por la descripción, que ahora se arma sola */
function textoDet(f){ return [f.estilo, f.descArchivo].filter(x=>String(x || '').trim()).join(' '); }
function detectarFicha(f, palabras){
  const d = detectarCon(textoDet(f), f.comp, f.tallas, palabras, f.marca);
  const uso = String(f.uso || '').trim();
  if (!uso) return d;
  if (!d.tipo){
    const cabeza = norm(uso).split(/\b(para|que|donde|con el que|for|to|used|sirve|se usa|which|that)\b/)[0];
    const dc = cabeza.trim() ? detectarCon(cabeza, {}, '', palabras, f.marca) : {};
    const du = dc.tipo ? dc : detectarCon(uso, {}, '', palabras, f.marca);
    if (du.tipo) d.tipo = du.tipo;
  }
  const d2 = detectar(textoDet(f) + ' ' + uso, f.comp, f.tallas, d.tipo || null);
  for (const [k, v] of Object.entries(d2)) if (d[k] === undefined && v !== undefined && k !== '_def') d[k] = v;
  if (d.tipo === 'calzado' && d.disenio === 'casual' && d2.disenio === 'entrenamiento') d.disenio = 'entrenamiento';
  return d;
}
function detectarCon(texto, comp, tallas, palabras, marca){
  const h = palabraDe(texto, palabras, marca);
  const d = detectar(texto, comp, tallas, h ? h.tipo : null);
  if (h){
    const def = d._def || [];
    PALABRA_ATTRS.forEach(k=>{ if (h[k] && (d[k] === undefined || def.includes(k))) d[k] = h[k]; });
    if (h.estiloCalz && d.tipo === 'calzado'){
      const imp = ATTR_BY.estiloCalz.implica[d.estiloCalz] || {};
      for (const [k,v] of Object.entries(imp)) if ((d[k] === undefined || def.includes(k)) && !h[k]) d[k] = v;
      if (d.estiloCalz !== 'tenis') delete d.disenio;
    }
    d._palabra = h.frase;
  }
  delete d._def;
  return d;
}
const NOMBRE_CALZ = {tenis:'TENIS', zapato:'ZAPATO', bota:'BOTA', botin:'BOTÍN', sandalia:'SANDALIA', slide:'SANDALIA TIPO SLIDE', chancla_tetones:'CHANCLA DE DEDO', pantufla:'PANTUFLA', mocasin:'MOCASÍN', tacon:'ZAPATO DE TACÓN',
  seguridad:'CALZADO DE SEGURIDAD', senderismo:'CALZADO DE SENDERISMO', tacos:'CALZADO DEPORTIVO CON TACOS', zueco:'ZUECO', bota_lluvia:'BOTA DE LLUVIA', acuatico:'CALZADO ACUÁTICO', esqui:'BOTA DE ESQUÍ', danza:'CALZADO DE DANZA', cubrecalzado:'CUBRECALZADO', roller:'CALZADO CON RUEDAS'};
const MAT_TXT = {plastico:'CAUCHO O PLÁSTICO', cuero:'CUERO', textil:'MATERIA TEXTIL', otro:'OTRAS MATERIAS', metal:'METAL', madera:'MADERA', papel:'PAPEL O CARTÓN', vidrio:'VIDRIO', paja:'PAJA'};
/* Descripción aduanal: solo qué es y la categoría de su material (textil,
   cuero o sintético), sin porcentajes ni detalles; luego para quién y la marca.
   Ej.: TENIS DE TEXTIL, UNISEX, MARCA VANS */
/* Otro producto: el nombre escrito en español o, si no, el texto de su subpartida */
function nombreOtro(f){
  const q = String(f.queEs || '').trim();
  if (q) return q.toUpperCase();
  const d = String(descDe(f.sacElegido) || '').split(/[;:]/)[0].replace(/^[-—\s]+/, '').trim();
  return (d || 'MERCANCÍA').toUpperCase();
}
const CAT_MAT = {textil:'TEXTIL', cuero:'CUERO', plastico:'MATERIAL SINTÉTICO', sintetica:'MATERIAL SINTÉTICO', artificial:'MATERIAL SINTÉTICO'};
function descripcionProfesional(f){
  const t = f.tipo; if (!t) return '';
  const g = grupoTipo(t), U = x => String(x || '').toUpperCase().trim();
  const e = edadDe(f), gen = f.genero;
  const para = e === 'bebe' ? 'PARA BEBÉ' : gen === 'M' ? (e === 'nino' ? 'PARA NIÑO' : 'PARA HOMBRE') : gen === 'F' ? (e === 'nino' ? 'PARA NIÑA' : 'PARA MUJER') : gen === 'U' ? (e === 'nino' ? 'PARA NIÑO O NIÑA' : 'UNISEX') : (e === 'nino' ? 'PARA NIÑO O NIÑA' : '');
  let nombre, cat = '';
  if (g === 'calzado'){
    nombre = NOMBRE_CALZ[f.estiloCalz] || 'CALZADO';
    cat = CAT_MAT[derivarCalzado(f).upper] || '';
  } else if (g === 'prenda'){
    nombre = t === 'chaqueta' ? ({chaleco_relleno:'CHALECO', chaleco:'CHALECO', reflectivo:'CHALECO REFLECTIVO', blazer:'SACO'})[f.hechura] || 'CHAQUETA'
      : t === 'pantalon' ? (f.largo === 'corto' ? 'PANTALÓN CORTO' : 'PANTALÓN')
      : t === 'camisa' || (t === 'camiseta' && f.polo) ? (f.polo ? 'CAMISA TIPO POLO' : 'CAMISA')
      : t === 'sudadera' ? (f.sueter ? 'SUÉTER' : 'SUDADERA')
      : t === 'gorra' ? ({sombrero:'SOMBRERO', gorro:'GORRO'})[f.formaTocado] || 'GORRA'
      : U(TIPO_CORTO_ES[t] || t);
    const c = parseComp((f.comp || {}).exterior || '');
    cat = c && c.pred ? (c.pred.grupo === 'cuero' ? 'CUERO' : f.recubierta ? 'MATERIAL SINTÉTICO' : 'TEXTIL') : '';
  } else if (g === 'bolso'){
    nombre = U(TIPO_CORTO_ES[t] || t);
    cat = CAT_MAT[f.exterior] || '';
  } else {
    nombre = t === 'otro_sac' ? nombreOtro(f) : U(TIPO_CORTO_ES[t] || t);
    const parte = partesDe(t, f).includes('exterior') ? 'exterior' : 'material';
    const cm = claseMat(f, parte);
    cat = cm ? (CAT_MAT[cm.pred] || MAT_TXT[cm.pred] || U(cm.pred)) : '';
  }
  const ext = [];
  if (para) ext.push(para);
  if (f.marca) ext.push('MARCA ' + U(f.marca));
  return [nombre + (cat ? ' DE ' + cat : '')].concat(ext).join(', ');
}
function derivarCalzado(f){
  const c = f.comp || {};
  const corte = parseMat(c.corte || '', 'corte'), suela = parseMat(c.suela || '', 'suela');
  return {corte, suela, upper: (corte && corte.pred) || f.upper || '', sole: (suela && suela.pred) || f.sole || '',
    upperComp: !!(corte && corte.pred), soleComp: !!(suela && suela.pred)};
}

/* ---------- Motor de reglas ---------- */
const FUND = {
  prenda:tr('GRI 1 and 6; Note 2 and Subheading Note 2 to Section XI (predominating textile material) and the notes to chapters 61 and 62.'),
  calzado:tr('GRI 1 and 6; Note 4 to chapter 64 (the upper is the material with the largest external surface, excluding accessories and reinforcements; the sole, the material with the largest surface in contact with the ground) and Subheading Note 1 to chapter 64 (sports footwear).'),
  bolso:tr('GRI 1 and 6; text of heading 42.02 and its subheadings, which split by outer surface.'),
  general:tr('GRI 1 (text of the heading and the section and chapter notes) and GRI 6 (subheadings).')
};
function clasificarReglas(f){
  const comp0 = (f.comp && f.comp.exterior) || f.composicion || (/%/.test(textoDet(f)) ? textoDet(f) : '');
  const comp = parseComp(comp0);
  const pred = comp ? comp.pred : null;
  const R = {codigo:null, razones:[], alternativas:[], avisos:[], faltantes:[], conf:3, comp, fundamento:FUND.general};
  const media = m => { R.conf = Math.min(R.conf, 2); if (m) R.faltantes.push(m); };
  const alt = (c, cuando) => { if (c) R.alternativas.push({codigo:c, cuando}); };
  const t = f.tipo;
  if (!t){ R.conf = 0; R.faltantes.push(tr('Choose the product type')); return fin(R); }
  if (t === 'otro_sac'){
    // Cualquier producto: la subpartida la elige quien llena la ficha en el SAC
    // oficial; el motor pone sus notas y los códigos nacionales que aplican
    const c = digits(f.sacElegido).slice(0, 6);
    if (c.length < 6){ R.conf = 0; R.faltantes.push(tr('Choose the SAC subheading')); return fin(R); }
    R.codigo = c; R.conf = 2; R.fundamento = tr('General Interpretative Rules 1 and 6: the text of the heading and subheading, and the section and chapter notes.');
    const propio = String(descDe(c) || '').split('—').slice(-1)[0].trim();
    R.razones.push(tr('Subheading chosen in the SAC: {0}{1}', [fmtCode(c), propio ? ' — ' + propio : '']));
    R.avisos.push(tr('Check it against the section, chapter and explanatory notes of heading {0} before sending it.', [c.slice(0, 4)]));
    return fin(R);
  }
  const grp = grupoTipo(t);

  function conFibra(opts){
    if (!pred || pred.grupo === 'cuero'){
      R.codigo = Object.values(opts)[0].slice(0,4);
      R.conf = Math.min(R.conf, 1);
      R.faltantes.push(tr('The outer fabric composition is missing; it is needed to choose the subheading'));
      for (const [k,c] of Object.entries(opts)) alt(c, tr('If the predominant fiber is {0}', [OPT_LBL[k]]));
      return;
    }
    const c = pickSub(opts, pred);
    R.codigo = c;
    let r = tr('Predominant fiber: {0} ({1}%)', [FIB_LBL[pred.grupo], pred.pct]);
    if (pred.mezclaMM) r += tr('; synthetic and artificial fibers are added together as one group when comparing');
    if (pred.empate) r += tr('; in a tie, the material that comes last in numerical order is taken');
    if (opts.demas === c && ['sintetica','artificial','lana','seda'].includes(pred.grupo)) r += tr('; this heading does not split it out, so it goes under "other textile materials"');
    R.razones.push(r + ' → ' + fmtCode(c));
    if (comp && comp.usoSegmento) R.razones.push(tr('The outer fabric is used{0}; lining and fill do not count', [comp.segmento ? ' ("' + comp.segmento + '")' : '']));
  }

  if (grp === 'prenda'){
    R.fundamento = FUND.prenda;
    const pmExt = (!pred || pred.grupo === 'otra') ? parseMat(comp0, 'corte') : null;
    if (pmExt && pmExt.pred === 'plastico' && t !== 'brasier'){ R.codigo = '392620'; R.razones.push(tr('The material is plastic with no textile fibers (for example, a PVC poncho) → 3926.20, plastic garments')); R.avisos.push(tr('If the plastic sheet is on a fabric, it is classified as a garment of coated fabric (6113 or 6210).')); return fin(R); }
    if (pred && pred.grupo === 'cuero' && t !== 'guantes'){ R.codigo = '420310'; R.razones.push(tr('The predominant material is leather: leather garments go in heading 4203, not in chapters 61 or 62')); return fin(R); }
    if (t === 'brasier'){ R.codigo = '621210'; R.razones.push(tr('Bras and bra-type sports tops → 6212.10, knitted or not and regardless of fiber')); return fin(R); }
    const defTej = {camiseta:'punto',sudadera:'punto',calcetines:'punto',guantes:'punto',bufanda:'punto',ropa_interior:'punto',chaqueta:'plano',pantalon:'plano',camisa:'plano',falda:'plano',vestido:'plano',conjunto:'punto',traje_bano:'punto',enterizo:'plano'}[t];
    let tej = t === 'calcetines' ? 'punto' : f.tejido;
    const defTej2 = t === 'bufanda' && f.tipoBufanda === 'bandana' ? 'plano' : null;
    if (!tej){
      tej = defTej2 || defTej;
      if (['camiseta','sudadera','guantes','bufanda','calcetines'].includes(t)) R.razones.push(tr('Fabric not given: knitted is assumed, as usual for this type'));
      else media(tr('Fabric not given: assumed {0}, the most common for this type', [tej === 'punto' ? 'knitted' : 'woven']));
    }
    if (t !== 'calcetines') R.razones.push(tej === 'punto' ? tr('Knitted fabric → chapter 61') : tr('Woven fabric → chapter 62'));
    if (f.edad === 'bebe'){
      R.razones.push(tr('Baby garment (up to 86 cm tall): the notes to chapters 61 and 62 send it to {0} with priority over other headings', [tej === 'punto' ? '6111' : '6209']));
      conFibra(tej === 'punto' ? {algodon:'611120',sintetica:'611130',demas:'611190'} : {algodon:'620920',sintetica:'620930',demas:'620990'});
      return fin(R);
    }
    const needsG = (['camisa','chaqueta','pantalon','ropa_interior','traje_bano'].includes(t) && !(t === 'chaqueta' && tej === 'punto' && f.hechura === 'chaleco') && !(t === 'chaqueta' && tej === 'punto' && f.hechura === 'reflectivo') && !(t === 'ropa_interior' && tej === 'punto' && f.prendaInt === 'camiseta_int')) || (['camiseta','sudadera','conjunto','enterizo'].includes(t) && tej === 'plano') || (t === 'camiseta' && f.polo);
    let g = f.genero;
    if (g !== 'M' && g !== 'F'){
      if (needsG){
        if (g === 'U') R.razones.push(tr('Unisex: the notes to chapters 61 and 62 classify as women\'s whatever is not identifiable as men\'s'));
        else media(tr('Say whether it is men\'s or women\'s (without it, the rule treats it as women\'s)'));
      }
      g = 'F';
    }
    const rec = !!f.recubierta && ['chaqueta','pantalon','camisa','sudadera','camiseta','conjunto','enterizo'].includes(t) && f.hechura !== 'blazer';
    if (rec){
      if (tej === 'punto') R.codigo = '611300';
      else if (t === 'chaqueta') R.codigo = g === 'M' ? '621020' : '621030';
      else R.codigo = g === 'M' ? '621040' : '621050';
      R.razones.push(tr('Fabric coated or laminated with plastic (headings 5903, 5906, 5907) → {0}', [fmtCode(R.codigo)]));
      R.avisos.push(tr('Only applies if the fabric qualifies under 5903: coating or lamination visible to the naked eye, for example. If the membrane is hidden between layers and does not qualify, use the alternative.'));
      const r2 = clasificarReglas(Object.assign({}, f, {recubierta:false}));
      if (r2.codigo) alt(r2.codigo, tr('If the fabric does not qualify as coated or laminated'));
      if (f.recubiertaAuto) media(tr('The coating was detected from the description; confirm it with the technical sheet'));
      return fin(R);
    }
    const O6101 = {algodon:'610120',manmade:'610130',demas:'610190'}, O6102 = {lana:'610210',algodon:'610220',manmade:'610230',demas:'610290'};
    const O6201 = {lana:'620120',algodon:'620130',manmade:'620140',demas:'620190'}, O6202 = {lana:'620220',algodon:'620230',manmade:'620240',demas:'620290'};
    const O6105 = {algodon:'610510',manmade:'610520',demas:'610590'}, O6106 = {algodon:'610610',manmade:'610620',demas:'610690'};
    const O6205 = {algodon:'620520',manmade:'620530',demas:'620590'}, O6206 = {seda:'620610',lana:'620620',algodon:'620630',manmade:'620640',demas:'620690'};
    const O6110 = {lana:'611011',algodon:'611020',manmade:'611030',demas:'611090'};
    const O6211M = {algodon:'621132',manmade:'621133',demas:'621139'}, O6211F = {algodon:'621142',manmade:'621143',demas:'621149'};
    switch (t){
      case 'camiseta':
        if (tej === 'plano'){ R.razones.push(tr('6109 only covers knitted garments; in woven fabric it is treated as a shirt → {0}', [g === 'M' ? '6205' : '6206'])); conFibra(g === 'M' ? O6205 : O6206); }
        else if (f.polo){ R.razones.push(tr('It has a collar and a buttoned placket: it is a polo, not a T-shirt → {0}', [g === 'M' ? '6105' : '6106'])); conFibra(g === 'M' ? O6105 : O6106); alt(pickSub({algodon:'610910',demas:'610990'}, pred), tr('If it actually has no collar or buttons')); }
        else { R.razones.push(tr('Knitted T-shirt, tank top or base layer → heading 6109 (no gender split)')); conFibra({algodon:'610910',demas:'610990'}); alt(pickSub(g === 'M' ? O6105 : O6106, pred), tr('If it has a collar and a buttoned placket at the neck (polo style)')); }
        break;
      case 'camisa':
        if (tej === 'punto'){ R.razones.push(g === 'M' ? tr('Knitted shirt or polo, men\'s → 6105') : tr('Knitted shirt, blouse or polo, women\'s → 6106')); conFibra(g === 'M' ? O6105 : O6106); }
        else { R.razones.push(g === 'M' ? tr('Woven shirt, men\'s → 6205') : tr('Woven shirt or blouse, women\'s → 6206')); conFibra(g === 'M' ? O6205 : O6206); }
        break;
      case 'sudadera':
        if (tej === 'punto' && f.hechuraSud === 'chaqueta_fleece'){ R.razones.push(tr('Fleece jacket worn over other garments → {0} (knitted jackets)', [g === 'M' ? '6101' : '6102'])); if (g !== 'M' && g !== 'F') media(); conFibra(g === 'M' ? O6101 : O6102); alt(pickSub(O6110, pred), tr('If its construction is closer to a sweater or sweatshirt than to outerwear')); media(tr('Fleece: the line between 6110 and 6101/6102 depends on construction; confirm it with photos or the sheet')); }
        else if (tej === 'punto'){ R.razones.push(tr('Knitted sweater, sweatshirt, hoodie or fleece → heading 6110 (no gender split)')); conFibra(O6110); alt(pickSub(g === 'M' ? O6101 : O6102, pred), tr('If it is built like an outer jacket (full zip, pockets, lining)')); if (f.hechuraSud === 'cierre') media(tr('Full zip: confirm it is not a fleece jacket (6101/6102)')); else if (!f.hechuraSud) media(tr('Give the construction: pullover, full zip or fleece jacket')); }
        else { R.razones.push(tr('Woven top with no more specific heading → 6211')); conFibra(g === 'M' ? O6211M : O6211F); alt(pickSub(g === 'M' ? O6201 : O6202, pred), tr('If it is built like a jacket or windbreaker')); }
        break;
      case 'chaqueta':
        if (f.hechura === 'blazer'){
          R.razones.push(tr('Suit jacket or blazer → {0}', [tej === 'punto' ? (g === 'M' ? '6103.3' : '6104.3') : (g === 'M' ? '6203.3' : '6204.3')]));
          conFibra(tej === 'punto' ? (g === 'M' ? {lana:'610331',algodon:'610332',sintetica:'610333',demas:'610339'} : {lana:'610431',algodon:'610432',sintetica:'610433',demas:'610439'}) : (g === 'M' ? {lana:'620331',algodon:'620332',sintetica:'620333',demas:'620339'} : {lana:'620431',algodon:'620432',sintetica:'620433',demas:'620439'}));
          break;
        }
        if (f.hechura === 'reflectivo'){
          if (tej === 'punto'){ R.razones.push(tr('Knitted (mesh) reflective safety vest → 6114, other knitted garments')); conFibra({algodon:'611420',manmade:'611430',demas:'611490'}); }
          else { R.razones.push(tr('Woven reflective safety vest → 6211, other garments')); conFibra(g === 'M' ? O6211M : O6211F); }
          R.avisos.push(tr('If the vest has fill or a jacket construction, it is classified as a padded vest or jacket.'));
          break;
        }
        if (f.hechura === 'chaleco'){
          if (tej === 'punto'){ R.razones.push(tr('Knitted vest without fill → 6110 (the heading includes vests)')); conFibra(O6110); alt(pickSub(g === 'M' ? O6101 : O6102, pred), tr('If it is built like warm outerwear')); }
          else { R.razones.push(tr('Woven vest without fill → 6211, other garments (the vests in headings 6201 and 6202 are the padded ones)')); conFibra(g === 'M' ? O6211M : O6211F); alt(pickSub(g === 'M' ? O6201 : O6202, pred), tr('If it is padded or built like a windbreaker')); }
          break;
        }
        if (!f.hechura) media(tr('Give the construction: jacket, vest with or without fill, reflective or blazer'));
        if (tej === 'punto'){
          R.razones.push(g === 'M' ? tr('Knitted jacket, anorak or vest, men\'s → 6101') : tr('Knitted jacket, anorak or vest, women\'s → 6102'));
          conFibra(g === 'M' ? O6101 : O6102);
          alt(pickSub(O6110, pred), tr('If it is a cardigan or light fleece, closer to a sweater than to outerwear'));
          alt('611300', tr('If the knitted fabric is coated or laminated with plastic'));
        } else {
          R.razones.push(g === 'M' ? tr('Woven jacket, anorak, parka or padded vest, men\'s → 6201') : tr('Woven jacket, anorak, parka or padded vest, women\'s → 6202'));
          conFibra(g === 'M' ? O6201 : O6202);
          alt(g === 'M' ? '621020' : '621030', tr('If the outer fabric is coated or laminated with plastic (some rain jackets)'));
          if (/\b(blazer|saco|sport ?coat|americana)\b/.test(norm(textoDet(f)))) alt(pickSub(g === 'M' ? {lana:'620331',algodon:'620332',sintetica:'620333',demas:'620339'} : {lana:'620431',algodon:'620432',sintetica:'620433',demas:'620439'}, pred), tr('If it is a dress suit jacket or blazer'));
        }
        if (f.relleno_tipo === 'plumon' || f.relleno_tipo === 'sintetico') R.razones.push(tr('The fill does not change the heading: the outer fabric governs'));
        break;
      case 'pantalon':
        if (tej === 'punto'){ R.razones.push(g === 'M' ? tr('Knitted pants, shorts or overalls, men\'s → 6103') : tr('Knitted pants, shorts or overalls, women\'s → 6104')); conFibra(g === 'M' ? {lana:'610341',algodon:'610342',sintetica:'610343',demas:'610349'} : {lana:'610461',algodon:'610462',sintetica:'610463',demas:'610469'}); alt('611300',tr('If the knitted fabric is coated or laminated with plastic')); }
        else { R.razones.push(g === 'M' ? tr('Woven pants, shorts or overalls, men\'s → 6203') : tr('Woven pants, shorts or overalls, women\'s → 6204')); conFibra(g === 'M' ? {lana:'620341',algodon:'620342',sintetica:'620343',demas:'620349'} : {lana:'620461',algodon:'620462',sintetica:'620463',demas:'620469'}); alt(g === 'M' ? '621040' : '621050',tr('If the fabric is coated or laminated with plastic (rain pants)')); }
        alt(g === 'M' ? (tej === 'punto' ? '611231' : '621111') : (tej === 'punto' ? '611241' : '621112'), tr('If they are shorts designed for swimming (boardshorts)'));
        break;
      case 'falda':
        R.razones.push(tej === 'punto' ? tr('Knitted skirt → 6104') : tr('Woven skirt → 6204'));
        conFibra(tej === 'punto' ? {lana:'610451',algodon:'610452',sintetica:'610453',demas:'610459'} : {lana:'620451',algodon:'620452',sintetica:'620453',demas:'620459'});
        break;
      case 'vestido':
        R.razones.push(tej === 'punto' ? tr('Knitted dress → 6104') : tr('Woven dress → 6204'));
        conFibra(tej === 'punto' ? {lana:'610441',algodon:'610442',sintetica:'610443',artificial:'610444',demas:'610449'} : {lana:'620441',algodon:'620442',sintetica:'620443',artificial:'620444',demas:'620449'});
        break;
      case 'enterizo':
        if (tej === 'punto'){ R.razones.push(tr('Knitted coverall, jumpsuit or romper → 6114, other knitted garments (no gender split)')); conFibra({algodon:'611420',manmade:'611430',demas:'611490'}); }
        else { R.razones.push(tr('Woven coverall or jumpsuit → 6211, other garments')); conFibra(g === 'M' ? O6211M : O6211F); }
        R.avisos.push(tr('Bib overalls go with pants; a one-piece ski suit goes in 6112.20 or 6211.20.'));
        break;
      case 'conjunto':
        if (f.esqui){ R.codigo = tej === 'punto' ? '611220' : '621120'; R.razones.push(tr('Ski or snowboard suit → {0}', [fmtCode(R.codigo)])); break; }
        if (tej === 'punto'){ R.razones.push(tr('Knitted tracksuit → 6112 (no gender split)')); conFibra({algodon:'611211',sintetica:'611212',demas:'611219'}); }
        else { R.razones.push(tr('Woven tracksuit → 6211')); conFibra(g === 'M' ? O6211M : O6211F); }
        R.avisos.push(tr('If the pieces are sold separately, each one is classified on its own.'));
        break;
      case 'traje_bano':
        if (tej === 'punto'){ R.razones.push(g === 'M' ? tr('Knitted swimwear, men\'s → 6112.3') : tr('Knitted swimwear, women\'s → 6112.4')); conFibra(g === 'M' ? {sintetica:'611231',demas:'611239'} : {sintetica:'611241',demas:'611249'}); }
        else { R.codigo = g === 'M' ? '621111' : '621112'; R.razones.push(tr('Woven swimwear → {0} (does not depend on fiber)', [fmtCode(R.codigo)])); }
        break;
      case 'ropa_interior':
        if (f.prendaInt === 'pijama'){
          if (tej === 'punto'){ R.razones.push(g === 'M' ? tr('Knitted pajamas, men\'s → 6107.2') : tr('Knitted pajamas or nightgown, women\'s → 6108.3')); conFibra(g === 'M' ? {algodon:'610721',manmade:'610722',demas:'610729'} : {algodon:'610831',manmade:'610832',demas:'610839'}); }
          else { R.razones.push(g === 'M' ? tr('Woven pajamas, men\'s → 6207.2') : tr('Woven pajamas or nightgown, women\'s → 6208.2')); conFibra(g === 'M' ? {algodon:'620721',manmade:'620722',demas:'620729'} : {algodon:'620821',manmade:'620822',demas:'620829'}); }
          break;
        }
        if (f.prendaInt === 'bata'){
          if (tej === 'punto'){ R.razones.push(g === 'M' ? tr('Knitted robe or bathrobe, men\'s → 6107.9') : tr('Knitted robe or bathrobe, women\'s → 6108.9')); conFibra(g === 'M' ? {algodon:'610791', demas:'610799'} : {algodon:'610891', manmade:'610892', demas:'610899'}); }
          else { R.razones.push(g === 'M' ? tr('Woven robe or bathrobe, men\'s → 6207.9') : tr('Woven robe or bathrobe, women\'s → 6208.9')); conFibra(g === 'M' ? {algodon:'620791', demas:'620799'} : {algodon:'620891', manmade:'620892', demas:'620899'}); }
          break;
        }
        if (f.prendaInt === 'camiseta_int'){
          if (tej === 'punto'){ R.razones.push(tr('Knitted undershirt → 6109 (no gender split)')); conFibra({algodon:'610910',demas:'610990'}); }
          else { R.razones.push(g === 'M' ? tr('Woven undershirt, men\'s → 6207.9') : tr('Woven undershirt, women\'s → 6208.9')); conFibra(g === 'M' ? {algodon:'620791',demas:'620799'} : {algodon:'620891',manmade:'620892',demas:'620899'}); }
          break;
        }
        if (tej === 'punto'){ R.razones.push(g === 'M' ? tr('Knitted boxers or briefs → 6107') : tr('Knitted panties or briefs → 6108')); conFibra(g === 'M' ? {algodon:'610711',manmade:'610712',demas:'610719'} : {algodon:'610821',manmade:'610822',demas:'610829'}); }
        else { R.razones.push(g === 'M' ? tr('Woven underpants → 6207') : tr('Woven underwear, women\'s → 6208')); conFibra(g === 'M' ? {algodon:'620711',demas:'620719'} : {algodon:'620891',manmade:'620892',demas:'620899'}); }
        break;
      case 'calcetines':
        R.razones.push(tr('Knitted socks → heading 6115'));
        conFibra({lana:'611594',algodon:'611595',sintetica:'611596',demas:'611599'});
        R.avisos.push(tr('Graduated compression hosiery goes in 6115.10.'));
        break;
      case 'guantes':
        if (pred && pred.grupo === 'cuero'){ R.codigo = f.guanteDeporte ? '420321' : '420329'; R.razones.push(f.guanteDeporte ? tr('Leather gloves designed for sports → 4203.21') : tr('Leather gloves (work or dress) → 4203.29')); R.fundamento = FUND.general; break; }
        if (tej === 'plano'){ R.codigo = '621600'; R.razones.push(tr('Woven gloves → 6216.00')); break; }
        if (f.recubierta){ R.codigo = '611610'; R.razones.push(tr('Knitted gloves coated or impregnated with plastic or rubber → 6116.10')); break; }
        R.razones.push(tr('Knitted gloves → heading 6116'));
        conFibra({lana:'611691',algodon:'611692',sintetica:'611693',demas:'611699'});
        break;
      case 'bufanda':
        if (f.tipoBufanda === 'bandana' && tej !== 'punto'){ R.razones.push(tr('Handkerchief or bandana up to 60 cm per side → 6213')); conFibra({algodon:'621320',demas:'621390'}); alt(pickSub({seda:'621410',lana:'621420',sintetica:'621430',artificial:'621440',demas:'621490'}, pred), tr('If any side is longer than 60 cm')); break; }
        if (tej === 'punto'){ R.codigo = '611710'; R.razones.push(tr('Knitted scarf, neck warmer or gaiter → 6117.10 (does not depend on fiber)')); }
        else { R.razones.push(tr('Woven scarf → heading 6214')); conFibra({seda:'621410',lana:'621420',sintetica:'621430',artificial:'621440',demas:'621490'}); }
        break;
    }
    return fin(R);
  }

  if (grp === 'calzado' && f.estiloCalz === 'roller'){
    R.codigo = '950670'; R.razones.push(tr('Footwear with built-in wheels or skates: roller skates, including footwear with skates attached → 9506.70'));
    R.avisos.push(tr('If the wheels are removable and the shoe is worn normally without them, check chapter 64.')); alt('640299', tr('If the wheels are not a fixed part of the footwear'));
    return fin(R);
  }
  if (grp === 'calzado'){
    R.fundamento = FUND.calzado;
    const dv = derivarCalzado(f);
    const up = dv.upper, so = dv.sole || 'caucho', est = f.estiloCalz || '', altura = f.altura || '';
    const tob = altura === 'tobillo' || altura === 'rodilla';
    R.razones.push(tr('Footwear → chapter 64'));
    if (!up){
      R.codigo = '64'; R.conf = 1;
      R.faltantes.push(f.upperMixto ? tr('The upper combines leather and textile: give the upper percentages or choose the material with the largest external surface') : tr('Give the upper material (the one with the largest external surface) or its composition'));
      alt('6404',tr('If the upper is textile')); alt('6403',tr('If the upper is natural leather')); alt('6402',tr('If the upper is rubber or plastics'));
      return fin(R);
    }
    const origenUp = dv.upperComp ? tr(' (upper composition: {0})', [resumenMat(dv.corte)]) : tr(' (set by hand, no upper composition)');
    R.razones.push(tr('Upper of {0}{1} and sole of {2}{3} — chapter 64, note 4: upper by its largest outer surface, sole by the surface touching the ground', [MAT_LBL[up], origenUp, MAT_LBL[so], dv.soleComp ? '' : (f.sole ? tr(' (set by hand)') : tr(' (assumed)'))]));
    if (!dv.upperComp) media(tr('Enter the upper composition by surface; without it the upper material cannot be verified'));
    const metal = f.puntera === 'metalica';
    const conAltura = c => { if (!altura) media(tr('Say whether it covers the ankle: it changes the subheading')); return c; };
    if (up === 'plastico' && so === 'caucho' && f.impermeable){
      R.codigo = metal ? '640110' : conAltura(altura === 'tobillo' ? '640192' : '640199');
      R.razones.push(tr('Waterproof, with rubber or plastic upper and sole joined without stitches or rivets → 6401{0}', [altura === 'rodilla' ? tr('; covers the knee → 6401.99') : '']));
      alt(tob ? '640291' : '640299', tr('If the upper is stitched, riveted or nailed to the sole'));
    } else if (est === 'esqui' && so === 'caucho' && up !== 'otro'){
      R.codigo = up === 'cuero' ? '640312' : up === 'plastico' ? '640212' : '640411';
      R.razones.push(tr('Ski or snowboard footwear → {0}', [fmtCode(R.codigo)]));
    } else if (est === 'tacos' && so === 'caucho' && up !== 'otro'){
      R.codigo = up === 'cuero' ? '640319' : up === 'plastico' ? '640219' : '640411';
      R.razones.push(tr('Sports footwear in the strict sense (cleats, spikes, cycling, wrestling, boxing; chapter 64, subheading note 1) → {0}', [fmtCode(R.codigo)]));
    } else if (est === 'chancla_tetones' && up === 'plastico' && so === 'caucho'){
      R.codigo = '640220'; R.razones.push(tr('Straps attached to the sole by plugs (toe post) → 6402.20'));
    } else if (up === 'textil'){
      if (so === 'caucho'){
        if (est === 'tenis' && f.disenio === 'entrenamiento'){ R.codigo = '640411'; R.razones.push(tr('Sneaker with athletic or training design → 6404.11')); alt('640419',tr('If it is actually casual or fashion wear')); }
        else if (est === 'senderismo'){ R.codigo = '640419'; R.razones.push(tr('Hiking or trekking footwear with textile upper → 6404.19: it is not sports or training footwear in the sense of 6404.11')); alt('640411',tr('If it is actually trail running or training')); }
        else {
          R.codigo = '640419'; R.razones.push((est === 'tenis' ? tr('Sneaker: {0}', [f.disenio === 'skate' ? 'skate' : tr('casual or lifestyle')]) : tr('Non-athletic footwear')) + ' → 6404.19');
          if (est === 'tenis'){ alt('640411',tr('If it is for training, gym, tennis, basketball or similar')); if (!f.disenio) media(tr('Say whether the sneaker design is athletic or casual')); else media(tr('Casual versus athletic: check the design, the sole and how it is marketed')); }
        }
      } else if (so === 'cuero'){ R.codigo = '640420'; R.razones.push(tr('Leather sole → 6404.20')); }
      else { R.codigo = '640520'; R.razones.push(tr('Sole of another material (textile, wood, cork) → 6405.20')); }
    } else if (up === 'cuero'){
      if (metal){ R.codigo = '640340'; R.razones.push(tr('Metal protective toe cap → 6403.40')); }
      else if (so === 'otro'){ R.codigo = '640510'; R.razones.push(tr('Sole that is not rubber, plastics or leather → 6405.10')); }
      else if (so === 'cuero'){
        R.codigo = conAltura(tob ? '640351' : '640359'); R.razones.push((tob ? tr('Covers the ankle') : tr('Does not cover the ankle')) + ' → ' + fmtCode(R.codigo));
        if (est === 'sandalia' && f.rodeaDedo){ R.codigo = '640320'; R.razones.push(tr('Leather sole and upper of leather straps across the instep and around the big toe → 6403.20')); }
        else if (est === 'sandalia') alt('640320',tr('If the upper is leather straps across the instep and around the big toe'));
      } else {
        R.codigo = conAltura(tob ? '640391' : '640399'); R.razones.push((tob ? tr('Covers the ankle') : tr('Does not cover the ankle')) + ' → ' + fmtCode(R.codigo));
        if (est === 'tenis' && f.disenio === 'entrenamiento'){ R.razones.push(tr('With a leather upper, "sports footwear" (6403.19) is limited to footwear with cleats or spikes, or for skiing, skating, wrestling, boxing or cycling')); alt('640319',tr('If it has cleats or spikes, or is for skating, cycling, wrestling or boxing')); }
      }
    } else if (up === 'plastico'){
      if (so === 'caucho'){
        R.codigo = conAltura(tob ? '640291' : '640299'); R.razones.push((tob ? tr('Covers the ankle') : tr('Does not cover the ankle')) + ' → ' + fmtCode(R.codigo));
        if (est === 'tenis' && f.disenio === 'entrenamiento'){ R.razones.push(tr('With a rubber or plastic upper, "sports" (6402.19) is limited to footwear with cleats or spikes and to skating, cycling, wrestling or boxing footwear')); alt('640219',tr('If it has cleats or spikes, or is for skating, cycling, wrestling or boxing')); }
        if (est === 'bota_lluvia' && !f.impermeable) alt(tob ? '640192' : '640199', tr('If it is waterproof, with no stitches or rivets between upper and sole'));
        R.avisos.push(tr('Synthetic leather (fabric with a visible plastic layer) counts as plastic for the upper.'));
      } else { R.codigo = '640590'; R.razones.push(tr('Rubber or plastic upper with a sole of another material → 6405.90')); }
    } else { R.codigo = '640590'; R.razones.push(tr('Upper of another material → 6405.90')); }
    if (metal && !['640110','640340'].includes(R.codigo)) R.avisos.push(tr('A metal toe cap only has its own subheading in 6401.10 (waterproof) and 6403.40 (leather upper); here it does not change the code.'));
    if (dv.corte && dv.corte.mixto && !f.upper) R.avisos.push(tr('The upper mixes materials: classification follows the one with the largest external surface. Confirm the percentages are by surface, not by weight.'));
    return fin(R);
  }

  if (grp === 'bolso'){
    R.fundamento = FUND.bolso;
    let ext = matDerivado(f, 'exterior', {cuero:'cuero', textil:'textil', plastico:'plastico', otro:'otro'}) || f.exterior;
    if (!ext && pred) ext = pred.grupo === 'cuero' ? 'cuero' : (pred.grupo === 'otra' ? '' : 'textil');
    if (!ext){ ext = 'textil'; media(tr('Outer surface not given: textile was assumed')); }
    const M = {
      mochila:['420291','420292','420299',tr('Backpack → subheadings 4202.91 to 4202.99 (other containers)')],
      bolso_viaje:['420291','420292','420299',tr('Sports or travel bag (includes duffels, waist packs, lunch bags, toiletry bags and chalk bags) → 4202.91 to 4202.99')],
      bolso_mano:['420221','420222','420229',tr('Handbag → 4202.21 to 4202.29')],
      maleta:['420211','420212','420219',tr('Suitcase, trolley or briefcase → 4202.11 to 4202.19')],
      billetera:['420231','420232','420239',tr('Wallet, card holder or pocket case → 4202.31 to 4202.39')]
    }[t];
    R.codigo = ext === 'cuero' ? M[0] : (ext === 'otro' ? M[2] : M[1]);
    R.razones.push(tr('{0}, according to the outer surface', [M[3]]));
    R.razones.push(tr('Outer surface of {0} → {1}', [({textil:tr('textile material'),plastico:tr('plastic sheeting'),cuero:'leather',otro:tr('other material')})[ext], fmtCode(R.codigo)]));
    if (ext === 'textil' || ext === 'plastico') R.avisos.push(tr('Textile and plastic sheeting share a subheading in 4202.'));
    if (t === 'billetera') R.avisos.push(tr('Rigid plastic phone cases do not go in 4202 but as articles of plastic (3926.90).'));
    return fin(R);
  }
  if (grp === 'gorra'){
    if (f.casco){ R.codigo = '650610'; R.razones.push(tr('Protective helmet → 6506.10')); }
    else if (f.materialGorra === 'paja'){ R.codigo = '650400'; R.razones.push(tr('Straw or plaited hat → 6504.00')); }
    else if (f.materialGorra === 'otro'){ R.codigo = '650699'; R.razones.push(tr('Headwear of non-textile material → 6506.99')); alt('650500',tr('If it is fabric or knit')); }
    else { R.codigo = '650500'; R.razones.push(tr('Knitted or fabric cap, beanie or hat → 6505.00 (does not depend on fiber)')); alt('650699',tr('If the outer material is not textile')); }
    return fin(R);
  }
  if (grp === 'cinturon'){
    let m = matDerivado(f, 'material', {cuero:'cuero', textil:'textil', plastico:'plastico', otro:'otro', metal:'otro'}) || f.materialCinturon;
    if (!m){ const pm = parseMat(textoDet(f), 'corte'); if (pm && pm.pred) m = pm.pred === 'otro' ? '' : pm.pred; }
    if (m === 'cuero'){ R.codigo = '420330'; R.razones.push(tr('Leather belt → 4203.30')); }
    else if (m === 'textil'){ const tej = f.tejido || 'plano'; R.codigo = tej === 'punto' ? '611780' : '621710'; R.razones.push(tr('Textile belt, {0}', [tej === 'punto' ? tr('knitted → 6117.80') : tr('woven or webbing → 6217.10')])); if (!f.tejido) media(tr('Say whether the webbing is knitted or woven')); }
    else if (m === 'plastico'){ R.codigo = '392620'; R.razones.push(tr('Plastic or synthetic leather belt → 3926.20')); }
    else { R.codigo = null; R.conf = 1; R.faltantes.push(tr('Give the belt material')); alt('420330',tr('If it is leather')); alt('621710',tr('If it is fabric')); alt('392620',tr('If it is plastic or synthetic leather')); }
    return fin(R);
  }
  if (t === 'plantilla'){ R.codigo = '640690'; R.razones.push(tr('Insoles, heel cushions and other footwear parts → 6406.90')); return fin(R); }
  if (t === 'cordones'){ R.codigo = '630790'; R.razones.push(tr('Textile shoelaces with aglets → 6307.90')); media(); R.avisos.push(tr('If the laces are leather or plastic, the heading changes.')); return fin(R); }
  if (t === 'cuidado_calzado' && f.kitViaje){ R.codigo = '960500'; R.razones.push(tr('Travel set for shoe cleaning (several items in a case) → 9605.00')); media(tr('Applies if it comes as a travel set; loose products each go by their material')); alt('340510',tr('If it is only the cream or cleaner')); return fin(R); }
  if (t === 'avios'){
    const k = f.tipoAvio || '', m = f.materialAvio || '';
    if (!k){ R.conf = 1; R.faltantes.push(tr('Say whether it is a button, zipper, buckle, eyelet or rivet')); alt('960621',tr('Plastic button')); alt('960711',tr('Metal zipper')); alt('830890',tr('Metal buckle')); return fin(R); }
    if (k === 'boton'){ if (f.forradoTextil){ R.codigo = '960629'; R.razones.push(tr('Fabric-covered button → 9606.29')); } else if (m === 'plastico'){ R.codigo = '960621'; R.razones.push(tr('Uncovered plastic button → 9606.21')); } else if (m === 'metal'){ R.codigo = '960622'; R.razones.push(tr('Uncovered base-metal button → 9606.22')); } else { R.codigo = '960629'; R.razones.push(tr('Button of another material → 9606.29')); if (!m) media(tr('Give the button material')); } }
    else if (k === 'cremallera'){ if (m === 'metal'){ R.codigo = '960711'; R.razones.push(tr('Zipper with base-metal teeth → 9607.11')); } else { R.codigo = '960719'; R.razones.push(tr('Zipper with plastic or other teeth → 9607.19')); if (!m) media(tr('Give the tooth material')); } alt('960720',tr('If they are only parts (pulls, sliders)')); }
    else if (k === 'hebilla'){ if (m === 'metal'){ R.codigo = '830890'; R.razones.push(tr('Base-metal buckles and clasps → 8308.90')); } else { R.codigo = '392690'; R.razones.push(tr('Plastic buckle → 3926.90')); if (m && m !== 'plastico') media(tr('Check the material: a buckle goes by its material')); } }
    else if (k === 'ojete'){ R.codigo = m === 'metal' || !m ? '830810' : '392690'; R.razones.push(m === 'metal' || !m ? tr('Base-metal eyelets, hooks and eyes → 8308.10') : tr('Plastic eyelet → 3926.90')); }
    else if (k === 'remache'){ R.codigo = '830820'; R.razones.push(tr('Tubular or bifurcated base-metal rivets → 8308.20')); }
    return fin(R);
  }
  if (t === 'accesorio_pelo'){
    const k = f.tipoPelo || '', m = f.materialAvio || '';
    if (k === 'liga'){ const tej = f.tejido || 'punto'; R.codigo = tej === 'plano' ? '621710' : '611780'; R.razones.push(tr('Fabric hair tie or scrunchie: textile clothing accessory → {0}', [fmtCode(R.codigo)])); media(tr('If it is only rubber elastic without fabric, check heading 40.16')); alt('401699',tr('Uncovered rubber hair tie')); }
    else if (k === 'horquilla'){ R.codigo = '961590'; R.razones.push(tr('Hairpins and hair grips → 9615.90')); }
    else if (k === 'pasador'){ R.codigo = m === 'plastico' ? '961511' : '961519'; R.razones.push(tr('Hair slides, combs and similar {0}', [m === 'plastico' ? tr('of plastic or hard rubber → 9615.11') : tr('of other materials → 9615.19')])); if (!m) media(tr('Give the material')); if (m === 'textil') alt('611780',tr('If it is a fabric headband without a rigid frame')); }
    else { R.conf = 1; R.faltantes.push(tr('Say whether it is a hair clip, hairpin or hair tie')); alt('961511',tr('Plastic hair clip')); alt('611780',tr('Fabric hair tie')); }
    return fin(R);
  }
  if (t === 'correa_reloj'){
    const m = f.materialAvio || '';
    R.codigo = m === 'metal' ? '911320' : '911390'; R.razones.push(m === 'metal' ? tr('Base-metal watch strap → 9113.20') : tr('Watch strap of leather, textile, silicone or other material → 9113.90'));
    if (!m) media(tr('Give the strap material'));
    return fin(R);
  }
  if (t === 'peleteria'){
    if (f.pelNat === 'artificial'){ R.codigo = '430400'; R.razones.push(tr('Artificial fur and articles thereof → 4304.00')); R.avisos.push(tr('A fabric garment with only a faux fur trim or lining is classified as a garment, not here.')); }
    else if (f.pelNat === 'natural'){ R.codigo = f.esPrenda ? '430310' : '430390'; R.razones.push(f.esPrenda ? tr('Garments and clothing accessories of fur → 4303.10') : tr('Other articles of fur → 4303.90')); R.avisos.push(tr('Skins of some species require a CITES permit.')); }
    else { R.conf = 1; R.faltantes.push(tr('Say whether it is natural or faux fur')); alt('430400',tr('Faux fur')); alt('430310',tr('Natural fur garment')); }
    return fin(R);
  }
  if (t === 'hamaca'){
    if (f.hamacaRed){ R.codigo = '560890'; R.razones.push(tr('Textile net hammock → 5608.90')); }
    else { R.codigo = '630690'; R.razones.push(tr('Fabric hammock: textile camping article → 6306.90')); media(tr('Confirm with the tariff: some fabric hammocks are classified as other made-up textile articles (6307.90)')); alt('630790',tr('Other made-up textile articles')); }
    return fin(R);
  }
  if (t === 'cuidado_calzado'){
    const p = f.producto || '';
    if (p === 'cepillo'){ R.codigo = '960390'; R.razones.push(tr('Shoe brushes → 9603.90')); }
    else if (p === 'spray'){ R.codigo = '340510'; R.razones.push(tr('Shoe care preparations → 3405.10')); media(tr('Check the spray\'s safety data sheet')); R.avisos.push(tr('Some waterproofing or repellent sprays are classified by their chemical composition in other headings (for example 3809 or 3402).')); }
    else if (p === 'crema'){ R.codigo = '340510'; R.razones.push(tr('Polishes, creams, waxes and cleaners for footwear or leather → 3405.10')); }
    else { R.conf = 1; R.faltantes.push(tr('Say which product it is')); alt('340510',tr('Cream, polish or cleaner')); alt('960390',tr('Brush')); }
    return fin(R);
  }
  if (t === 'lentes_sol'){ R.codigo = '900410'; R.razones.push(tr('Sunglasses → 9004.10')); R.avisos.push(tr('Cases sold with the glasses follow the classification of the glasses.')); return fin(R); }
  if (t === 'sombrilla'){ R.codigo = f.telescopica ? '660191' : '660199'; R.razones.push(f.telescopica ? tr('Umbrella with telescopic shaft → 6601.91') : tr('Umbrella with fixed shaft → 6601.99')); return fin(R); }
  if (t === 'botella'){
    const m = f.alVacio ? 'acero_vacio' : f.materialBotella;
    const MB = {acero_vacio:['961700',tr('Vacuum-insulated thermos or container → 9617.00 (vacuum insulation governs, whatever the material)')], acero:['732393',tr('Stainless steel bottle without vacuum → 7323.93')], aluminio:['761510',tr('Aluminum bottle → 7615.10')], plastico:['392490',tr('Plastic bottle or tumbler: other household articles → 3924.90')]};
    if (MB[m]){ R.codigo = MB[m][0]; R.razones.push(MB[m][1]); if (m === 'plastico') alt('392410', tr('If it is presented as tableware')); }
    else { R.conf = 1; R.faltantes.push(tr('Give the material and whether it is vacuum insulated')); Object.values(MB).forEach(x=>alt(x[0], x[1].split(' → ')[0])); }
    return fin(R);
  }
  if (t === 'tienda' && f.esBase){ R.codigo = '630690'; R.razones.push(tr('Tent footprint or accessory: other camping goods → 6306.90')); return fin(R); }
  if (t === 'tienda'){ R.razones.push(tr('Tent → heading 6306')); conFibra({sintetica:'630622',demas:'630629'}); return fin(R); }
  if (t === 'saco'){ R.codigo = '940430'; R.razones.push(tr('Sleeping bags → 9404.30, whatever the fill')); return fin(R); }
  if (t === 'patineta'){ R.codigo = '950699'; R.razones.push(tr('{0} → 9506.99, which includes parts', [f.parteSkate === 'partes' ? tr('Skateboard wheels, trucks and other parts') : f.parteSkate === 'tabla' ? tr('Skateboard deck') : tr('Skateboard')])); return fin(R); }
  if (t === 'polainas'){ R.codigo = '640690'; R.razones.push(tr('Heading 64.06 expressly includes gaiters and similar articles → 6406.90')); return fin(R); }
  if (t === 'llavero'){
    const m = f.materialLlavero || '';
    const ML = {metal:['732690',tr('Base-metal keychain → 7326.90')], cuero:['420500',tr('Leather keychain → 4205.00, other articles of leather')], textil:['630790',tr('Lanyard or textile webbing keychain → 6307.90')], plastico:['392640',tr('Decorative plastic or rubber keychain → 3926.40')]};
    if (ML[m]){ R.codigo = ML[m][0]; R.razones.push(ML[m][1]); media(); if (m === 'metal') alt('711719',tr('If it is presented as costume jewelry')); if (m === 'plastico') alt('392690',tr('If it is not decorative')); if (m === 'textil') alt('560900', tr('If it is cord or rope (not woven webbing)')); }
    else { R.conf = 1; R.faltantes.push(tr('Give the keychain material')); Object.values(ML).forEach(x=>alt(x[0], x[1].split(' → ')[0])); }
    R.avisos.push(tr('If it has a bottle opener, flashlight or another function, the classification may change because of that function.'));
    return fin(R);
  }
  if (t === 'reloj'){
    const MR = {analogico:['910211',tr('Electric wristwatch with mechanical display (hands) → 9102.11')], digital:['910212',tr('Wristwatch with digital display → 9102.12')], combinado:['910219',tr('Watch with analog and digital display → 9102.19')], inteligente:['851762',tr('Smartwatch that receives and transmits data → 8517.62')]};
    const m = MR[f.pantalla];
    if (m){ R.codigo = m[0]; R.razones.push(m[1]); if (f.pantalla !== 'inteligente') R.avisos.push(tr('If the case is precious metal it goes in 9101; if it is mechanical (wind-up), in 9102.21 or 9102.29.')); else alt('910212',tr('If it only tells time and does not transmit data')); }
    else { R.conf = 1; R.faltantes.push(tr('Give the watch type')); Object.values(MR).forEach(x=>alt(x[0], x[1].split(' → ')[0])); }
    return fin(R);
  }
  if (t === 'colchoneta'){
    if (f.tipoColch === 'inflable'){ R.codigo = '630640'; R.razones.push(tr('Textile inflatable mattress → 6306.40')); alt('392690',tr('If it is all plastic')); }
    else if (f.tipoColch === 'espuma'){ R.codigo = '940429'; R.razones.push(tr('Foam or self-inflating pad → 9404.29, mattresses of other materials')); alt('630640',tr('If it inflates with air only, without foam')); media(); }
    else if (f.tipoColch === 'almohada'){ R.codigo = '940490'; R.razones.push(tr('Filled pillows and cushions → 9404.90')); alt('630640',tr('If it is an inflatable fabric pillow')); }
    else { R.conf = 1; R.faltantes.push(tr('Say whether it is inflatable or foam')); alt('630640',tr('Inflatable')); alt('940429',tr('Foam or self-inflating')); }
    return fin(R);
  }
  if (t === 'manta'){ R.razones.push(tr('Blankets → heading 6301 by fiber')); conFibra({lana:'630120',algodon:'630130',sintetica:'630140',demas:'630190'}); return fin(R); }
  if (t === 'mueble_camping'){
    if (f.mueble === 'mesa'){ const MM = {metal:['940320',tr('Table with metal frame → 9403.20')], madera:['940360',tr('Wooden table → 9403.60')], plastico:['940370',tr('Plastic table → 9403.70')]}[f.materialMueble]; if (MM){ R.codigo = MM[0]; R.razones.push(MM[1]); } else { R.conf = 1; R.faltantes.push(tr('Give the table material')); alt('940320',tr('Metal')); alt('940370',tr('Plastic')); } return fin(R); }
    R.codigo = f.acolchada ? '940171' : '940179'; R.razones.push(tr('Chair or seat with metal frame {0}', [f.acolchada ? tr('and fill → 9401.71') : tr('without fill → 9401.79')])); if (!f.acolchada) alt('940171',tr('If the seat or backrest has fill')); if (!f.mueble) media(tr('Say whether it is a chair or a table')); R.avisos.push(tr('If the frame is not metal (wood, plastic), the subheading changes.')); return fin(R);
  }
  if (t === 'toalla'){
    if (f.rizo && pred && pred.grupo === 'algodon'){ R.codigo = '630260'; R.razones.push(tr('Cotton terry towel → 6302.60')); return fin(R); }
    R.razones.push(tr('Towels of {0} → 6302.9', [f.rizo ? 'non-cotton terry' : tr('plain weave or microfiber')])); conFibra({algodon:'630291', manmade:'630293', demas:'630299'}); return fin(R);
  }
  if (t === 'mascota'){ R.codigo = '420100'; R.razones.push(tr('Collars, leashes, harnesses and coats for animals, of any material → 4201.00')); R.avisos.push(tr('Pet beds and toys do not go here: they are classified by what they are (9404, 9503, 6307).')); return fin(R); }
  if (t === 'bisuteria'){
    const MB = {metal:['711719',tr('Base-metal costume jewelry → 7117.19')], cuero:['420500',tr('Leather bracelet or accessory → 4205.00')], textil:['630790',tr('Textile bracelet or cord → 6307.90')], otro:['711790',tr('Costume jewelry of plastic, wood or other materials → 7117.90')]}[f.materialBisu];
    if (MB){ R.codigo = MB[0]; R.razones.push(MB[1]); if (f.materialBisu !== 'metal') media(); } else { R.conf = 1; R.faltantes.push(tr('Give the main material')); alt('711719',tr('Base metal')); alt('711790',tr('Plastic or other')); }
    R.avisos.push(tr('If it contains gold, silver or platinum, it goes in 7113 (jewelry).')); return fin(R);
  }
  if (t === 'parche'){
    const tp = f.tipoParche;
    if (tp === 'sticker'){ R.codigo = '491191'; R.razones.push(tr('Printed sticker or decal → 4911.91, printed pictures')); alt('490890',tr('If it is a transfer decal (a backing peels off and the image stays)')); media(); }
    else if (tp === 'bordado'){ R.razones.push(tr('Embroidered patch, with or without visible ground → 5810')); conFibra({algodon:'581091', manmade:'581092', demas:'581099'}); if (!pred){ R.codigo = '581092'; R.conf = 2; } }
    else if (tp === 'tejido'){ R.codigo = '580710'; R.razones.push(tr('Woven patch, badge or label → 5807.10')); }
    else if (tp === 'pvc'){ R.codigo = '392690'; R.razones.push(tr('PVC or rubber patch → 3926.90')); media(); alt('401699',tr('If it is vulcanized rubber')); }
    else { R.conf = 1; R.faltantes.push(tr('Say whether it is a sticker, embroidered, woven or PVC')); }
    return fin(R);
  }
  if (t === 'linterna'){ R.codigo = '851310'; R.razones.push(tr('Flashlights and headlamps with their own power source → 8513.10')); return fin(R); }
  if (t === 'equipo_deporte'){
    const A = {fitness:['950691',tr('Exercise or gym articles (yoga mat, bands, ropes) → 9506.91')], escalada:['950699',tr('Climbing equipment such as crash pads → 9506.99')], protecciones:['950699',tr('Knee pads, elbow pads and sports protection → 9506.99')], pelota:['950662',tr('Inflatable balls → 9506.62')], otro:['950699',tr('Other sports articles → 9506.99')]}[f.actividad];
    if (A){ R.codigo = A[0]; R.razones.push(A[1]); if (f.actividad === 'escalada') alt('950691',tr('If it is used as a gym mat')); if (f.actividad === 'protecciones') R.avisos.push(tr('Orthopedic or medical knee braces go in another heading (9021 or 6307).')); }
    else { R.codigo = '950699'; R.razones.push(tr('Sports equipment → 9506.99')); media(tr('Say what it is used for (exercise, climbing, protection, ball)')); }
    return fin(R);
  }
  if (t === 'bolsa_compra'){
    const B = {papel: f.baseAncha ? ['481930',tr('Paper sack or bag with a base of 40 cm or more → 4819.30')] : ['481940',tr('Paper bag → 4819.40')], plastico:['392321',tr('Plastic (polyethylene) bag → 3923.21')], tela:['420292',tr('Fabric shopping bag with handles → 4202.92')]}[f.materialBolsa];
    if (B){ R.codigo = B[0]; R.razones.push(B[1]); if (f.materialBolsa === 'plastico') alt('392329',tr('If it is not polyethylene (for example, PP or PVC)')); if (f.materialBolsa === 'tela') alt('630590',tr('If it is a packing sack without handles')); }
    else { R.conf = 1; R.faltantes.push(tr('Give the bag material')); alt('481940',tr('Paper')); alt('392321',tr('Plastic')); alt('420292',tr('Reusable fabric')); }
    return fin(R);
  }
  if (t === 'caja'){
    const C = {corrugado:['481910',tr('Corrugated cardboard box → 4819.10')], plegadizo:['481920',tr('Folding box of card stock or non-corrugated board → 4819.20')], plastico:['392310',tr('Plastic box → 3923.10')]}[f.materialCaja];
    if (C){ R.codigo = C[0]; R.razones.push(C[1]); } else { R.conf = 1; R.faltantes.push(tr('Say whether it is corrugated cardboard, card stock or plastic')); alt('481910',tr('Corrugated')); alt('481920',tr('Card stock')); }
    R.avisos.push(tr('Boxes that come with the goods they contain are classified with those goods (GRI 5).')); return fin(R);
  }
  if (t === 'gancho'){
    const G = {plastico:['392690',tr('Plastic hanger → 3926.90')], metal:['732620',tr('Iron or steel wire hanger → 7326.20')], madera:['442110',tr('Wooden hangers → 4421.10')]}[f.materialGancho];
    if (G){ R.codigo = G[0]; R.razones.push(G[1]); } else { R.conf = 1; R.faltantes.push(tr('Give the hanger material')); alt('392690',tr('Plastic')); alt('442110',tr('Wood')); }
    return fin(R);
  }
  if (t === 'etiqueta'){
    const E = {papel:['482110',tr('Printed paper or board labels → 4821.10')], tejida:['580710',tr('Woven labels → 5807.10')], plastico:['392690',tr('Plastic labels → 3926.90')]}[f.materialEtiqueta];
    if (E){ R.codigo = E[0]; R.razones.push(E[1]); } else { R.conf = 1; R.faltantes.push(tr('Say whether it is paper, woven or plastic')); alt('482110',tr('Paper')); alt('580710',tr('Woven')); }
    return fin(R);
  }
  if (t === 'exhibidor'){
    if (f.tipoExhib === 'maniqui'){ R.codigo = '961800'; R.razones.push(tr('Shop-window mannequins and busts → 9618.00')); return fin(R); }
    const X = {metal:['940320',tr('Metal fixture or display → 9403.20')], madera:['940360',tr('Wooden fixture or display → 9403.60')], plastico:['940370',tr('Plastic fixture or display → 9403.70')]}[f.materialMueble];
    if (X){ R.codigo = X[0]; R.razones.push(X[1]); media(); alt('961800',tr('If it is a mannequin or bust')); R.avisos.push(tr('If the display is a metal structure for wall or floor mounting with no furniture function, it may go as an article of metal (7326 or 7610).')); }
    else { R.conf = 1; R.faltantes.push(tr('Give the type and the material')); alt('940320',tr('Metal')); alt('961800',tr('Mannequin')); }
    return fin(R);
  }
  if (t === 'magnesio'){
    if (f.presentacion === 'liquido'){ R.codigo = '382499'; R.razones.push(tr('Liquid chalk: magnesium carbonate mixed with alcohol or others → 3824.99')); media(tr('Confirm the composition with the safety data sheet')); alt('283699',tr('If it is unmixed magnesium carbonate')); }
    else { R.codigo = '283699'; R.razones.push(tr('Climbing chalk (magnesium carbonate) → 2836.99')); media(tr('Confirm with the safety data sheet that it is magnesium carbonate without additives')); alt('382499',tr('If it is a mixture with additives')); }
    return fin(R);
  }
  if (t === 'bastones'){ R.codigo = '950699'; R.razones.push(tr('Trekking or hiking poles: outdoor sports equipment → 9506.99')); alt('660200',tr('If they are presented as equipment for a specific sport (for example, ski poles)')); media(); return fin(R); }
  return fin(R);
}
function fin(R){
  const d = digits(R.codigo);
  if (d && d.length < 6) R.conf = Math.min(R.conf, 1);
  R.confianza = [tr('no data'),'low','medium','high'][R.conf];
  const seen = new Set([d]);
  R.alternativas = R.alternativas.filter(a=>{ const k = digits(a.codigo); if (!k || seen.has(k)) return false; seen.add(k); return true; });
  return R;
}

/* ---------- Aprendizaje ---------- */
const STOP = new Set(['de','la','el','los','las','con','para','por','del','al','the','and','of','with','for','an','ua','mn','wm','mens','men','womens','women','hombre','mujer','unisex','talla','size','xs','xl','xxl','xxxl','ss','ls']);
function tokens(s){ return [...new Set(norm(s).split(/[^a-z0-9]+/).filter(w=>w.length >= 2 && !STOP.has(w)))]; }
function perfilDe(f, comp){
  const g = grupoTipo(f.tipo), p = [f.tipo || '?'];
  const fib = comp && comp.pred ? comp.pred.grupo : '?';
  if (g === 'prenda') p.push(f.tipo === 'calcetines' ? 'punto' : (f.tejido || '?'), f.genero === 'M' ? 'M' : 'F', f.edad === 'bebe' ? 'bebe' : '-', f.recubierta ? 'rec' : '-', fib, f.esqui ? 'esqui' : '-', f.hechura || f.hechuraSud || f.prendaInt || f.tipoBufanda || (f.polo ? 'polo' : '-'));
  else if (g === 'calzado'){ const dv = derivarCalzado(f); p.push(f.estiloCalz || '?', dv.upper || '?', dv.sole || 'caucho', f.altura || '?', f.disenio || '-', f.puntera === 'metalica' ? 'pm' : '-', f.impermeable ? 'imp' : '-'); }
  else if (g === 'bolso') p.push(f.exterior || (fib === 'cuero' ? 'cuero' : 'textil'));
  else if (g === 'gorra') p.push(f.casco ? 'casco' : (f.materialGorra || 'textil'));
  else if (g === 'cinturon') p.push(f.materialCinturon || '?', f.tejido || '-');
  else if (f.tipo === 'botella') p.push(f.materialBotella || '?');
  else if (f.tipo === 'sombrilla') p.push(f.telescopica ? 'tel' : '-');
  else if (f.tipo === 'cuidado_calzado') p.push(f.producto || '?');
  else if (f.tipo === 'llavero') p.push(f.materialLlavero || '?');
  else if (f.tipo === 'avios') p.push(f.tipoAvio || '?', f.materialAvio || '?', f.forradoTextil ? 'forr' : '-');
  else if (f.tipo === 'accesorio_pelo') p.push(f.tipoPelo || '?', f.materialAvio || '?');
  else if (f.tipo === 'correa_reloj') p.push(f.materialAvio || '?');
  else if (f.tipo === 'peleteria') p.push(f.pelNat || '?', f.esPrenda ? 'prenda' : '-');
  else if (f.tipo === 'hamaca') p.push(f.hamacaRed ? 'red' : 'tela');
  else if (f.tipo === 'tienda') p.push(f.esBase ? 'base' : '-');
  else if (f.tipo === 'bolsa_compra') p.push(f.materialBolsa || '?', f.baseAncha ? 'b40' : '-');
  else if (f.tipo === 'reloj') p.push(f.pantalla || '?');
  else if (f.tipo === 'colchoneta') p.push(f.tipoColch || '?');
  else if (f.tipo === 'magnesio') p.push(f.presentacion || '?');
  else if (f.tipo === 'mueble_camping') p.push(f.mueble || '?', f.acolchada ? 'acol' : '-', f.materialMueble || '-');
  else if (f.tipo === 'exhibidor') p.push(f.tipoExhib || '?', f.materialMueble || '-');
  else if (['bisuteria','parche','equipo_deporte','bolsa_compra','caja','gancho','etiqueta'].includes(f.tipo)) p.push(f.materialBisu || f.tipoParche || f.actividad || f.materialBolsa || f.materialCaja || f.materialGancho || f.materialEtiqueta || '?');
  else if (f.tipo === 'toalla') p.push(f.rizo ? 'rizo' : '-', fib);
  else if (f.tipo === 'manta') p.push(fib);
  else if (f.tipo === 'tienda') p.push(fib);
  return p.join('|');
}
function perfilLegible(p){
  const parts = p.split('|'); const t = parts[0];
  const L = {punto:'knitted',plano:'woven',M:'men',F:'women',bebe:'baby',rec:'coated',esqui:'ski',tob:tr('covers ankle'),tobillo:tr('covers ankle'),rodilla:tr('covers knee'),bajo:tr('low cut'),pm:tr('metal toe cap'),imp:'waterproof',casco:'helmet',tel:'telescopic',
    textil:'textile',cuero:'leather',plastico:tr('rubber or plastics'),otro:tr('other material'),caucho:tr('rubber or plastic sole'),casual:'casual',entrenamiento:'athletic',skate:'skate',
    lana:'wool',seda:'silk',algodon:'cotton',vegetal:tr('vegetable fiber'),sintetica:'synthetic',artificial:'artificial',otra:tr('other fiber'),
    chaleco_relleno:tr('padded vest'),chaleco:tr('vest without fill'),reflectivo:'reflective',blazer:'blazer',pullover:'pullover',cierre:tr('full zip'),chaqueta_fleece:tr('fleece jacket'),interior:'underwear',pijama:'pajamas',camiseta_int:'undershirt',bandana:'bandana',polo:'polo',senderismo:'hiking',tacon:tr('high heel'),zueco:'clog',acuatico:tr('water shoe'),paja:'straw',metal:'metal',inflable:'inflatable',espuma:'foam',polvo:'powder',liquido:'liquid',acol:'padded',analogico:'analog',digital:'digital',combinado:tr('analog and digital'),inteligente:'smart',acero_vacio:tr('vacuum thermos'),acero:'steel',aluminio:'aluminum',crema:'cream',spray:'spray',cepillo:'brush',tenis:'sneaker',bota:'boot',botin:tr('ankle boot'),zapato:'shoe',mocasin:'moccasin',sandalia:'sandal',slide:'slide',chancla_tetones:'flip-flop',pantufla:'slipper',seguridad:'safety',bota_lluvia:tr('rain boot'),tacos:tr('with cleats')};
  return [TIPO_CORTO[t] || t].concat(parts.slice(1).map(x=>L[x]).filter(Boolean));
}
function similitud(rec, f, toks, perfil){
  const sk = norm(f.estilo || f.sku || '').trim(), rk = norm(rec.estilo || rec.sku || '').trim();
  if (sk && rk && sk === rk) return 1;
  const tf = textoDet(f), trx = textoDet(rec);
  if (tf && trx && norm(tf).trim() === norm(trx).trim() && rec.tipo === f.tipo) return 0.97;
  const tr = rec._tok || (rec._tok = tokens(trx));
  const inter = tr.filter(x=>toks.includes(x)).length;
  const uni = new Set(tr.concat(toks)).size || 1;
  const jac = inter / uni;
  let attr = 0;
  if (rec.tipo && rec.tipo === f.tipo){
    const a = (rec.perfil || '').split('|'), b = perfil.split('|');
    const n = Math.max(a.length, b.length, 1); let m = 0;
    for (let i = 0; i < n; i++) if (a[i] === b[i]) m++;
    attr = m / n;
  }
  return 0.6 * jac + 0.4 * attr;
}
function sugerir(f, recs, incisos, excluirId){
  const regla = clasificarReglas(f);
  const perfil = perfilDe(f, regla.comp);
  const toks = tokens(textoDet(f));
  const conCodigo = recs.filter(r=>r.id !== excluirId && digits(r.codigo).length >= 6);
  const parecidos = f.tipo || toks.length ? conCodigo.map(r=>({r, s:similitud(r, f, toks, perfil)})).filter(x=>x.s >= 0.3).sort((a,b)=>b.s - a.s).slice(0,4) : [];
  const mismos = conCodigo.filter(r=>r.perfil === perfil);
  const tally = {};
  mismos.forEach(r=>{ const c = digits(r.codigo).slice(0,6); tally[c] = (tally[c]||0) + 1; });
  const top = Object.entries(tally).sort((a,b)=>b[1] - a[1])[0];
  const out = Object.assign({}, regla, {
    fuente:'regla', perfil, parecidos,
    razones: regla.razones.slice(), alternativas: regla.alternativas.slice(),
    razonesRegla: regla.razones.slice(), codigoRegla: regla.codigo,
    aprendido: top ? {codigo: top[0], n: top[1], total: mismos.length} : null
  });
  const d6 = c => digits(c).slice(0,6);
  const casi = parecidos[0] && parecidos[0].s >= 0.9 && (!f.tipo || !parecidos[0].r.tipo || parecidos[0].r.tipo === f.tipo) ? parecidos[0] : null;
  if (casi){
    out.codigo = d6(casi.r.codigo); out.fuente = 'historial'; out.conf = 3;
    out.razones = [tr('You already classified this product ("{0}") as {1}', [casi.r.desc || casi.r.estilo, fmtCode(casi.r.codigo)])];
    if (d6(casi.r.codigo) !== d6(regla.codigo) && regla.codigo) out.alternativas = [{codigo: regla.codigo, cuando:tr('By the general rules')}].concat(regla.alternativas);
    out.faltantes = []; out.avisos = [];
    out.completo = digits(casi.r.codigo).length > 6 ? digits(casi.r.codigo) : null;
  } else if (top && top[0] !== d6(regla.codigo) && regla.codigo){
    out.codigo = top[0]; out.fuente = 'criterio';
    out.conf = top[1] >= 3 ? 3 : 2;
    out.razones = [tr('You have classified {0}{1} with this same profile in {2}{3}', [top[1], top[1] === 1 ? ' product' : ' products', fmtCode(top[0]), mismos.length > top[1] ? tr(' (out of {0} in total)', [mismos.length]) : ''])];
    out.alternativas = [{codigo: regla.codigo, cuando:tr('By the general rules')}].concat(regla.alternativas);
  } else if (top && top[0] === d6(regla.codigo)){
    out.conf = Math.max(out.conf, top[1] >= 2 ? 3 : out.conf);
    out.razones.push(tr('Matches {0}{1} with this same profile', [top[1], top[1] === 1 ? tr(' of your classifications') : tr(' of your classifications')]));
  }
  const c6 = d6(out.codigo);
  if (c6.length === 6){
    const inc = incisos[c6];
    if (inc && digits(inc.inciso).length > 6){ out.completo = digits(inc.inciso); out.dai = inc.dai; out.incNota = inc.nota; }
    else if (!out.completo){
      const last = conCodigo.filter(r=>d6(r.codigo) === c6 && digits(r.codigo).length > 6).sort((a,b)=>(b.tsMod||b.ts||0) - (a.tsMod||a.ts||0))[0];
      if (last) out.completo = digits(last.codigo);
    }
  }
  const seen = new Set([c6]);
  out.alternativas = out.alternativas.filter(a=>{ const k = digits(a.codigo); if (!k || seen.has(k)) return false; seen.add(k); return true; });
  if (digits(out.codigo).length && digits(out.codigo).length < 6) out.conf = Math.min(out.conf, 1);
  out.confianza = [tr('no data'),'low','medium','high'][out.conf];
  return out;
}

/* ---------- Origen y acuerdos ---------- */
const PAISES = [tr('El Salvador'),tr('Guatemala'),tr('Honduras'),tr('Nicaragua'),tr('Costa Rica'),tr('Panama'),tr('Dominican Republic'),tr('Mexico'),tr('United States'),tr('Colombia'),tr('Chile'),tr('Brazil'),tr('Peru'),tr('China'),tr('Vietnam'),tr('Cambodia'),tr('Indonesia'),tr('Bangladesh'),tr('India'),tr('Pakistan'),tr('Sri Lanka'),tr('Thailand'),tr('Philippines'),tr('Myanmar'),tr('Taiwan'),tr('South Korea'),tr('Japan'),tr('Turkey'),tr('Jordan'),tr('Egypt'),tr('Slovenia'),tr('Italy'),tr('Portugal'),tr('Spain'),tr('Germany'),tr('France'),tr('Romania'),tr('Poland'),tr('United Kingdom')];
const ACUERDO_OPC = [['',tr('No trade agreement')],['mcca',tr('Central American Common Market')],['cafta','CAFTA-DR'],['mexico',tr('Central America–Mexico FTA')],['panama',tr('Central America–Panama FTA')],['tlc',tr('Other FTA in force (Chile, Colombia, Taiwan, Korea)')],['ue',tr('EU–Central America Association Agreement')],['uk',tr('UK–Central America Association Agreement')]];
const ACUERDO_TXT = {
  mcca:tr('Central American Common Market: normally free of import duty if it meets the Central American rules of origin'),
  cafta:tr('CAFTA-DR: preference may apply if it meets the treaty\'s rules of origin (for textiles, usually the yarn-forward rule)'),
  mexico:tr('Central America–Mexico FTA: preference may apply with a certificate of origin'),
  panama:tr('Central America–Panama FTA: preference may apply with a certificate of origin'),
  tlc:tr('There is an FTA in force with El Salvador: check whether the product is in the tariff elimination schedule'),
  ue:tr('EU–Central America Association Agreement: preference may apply with proof of origin'),
  uk:tr('UK–Central America Association Agreement: preference may apply with proof of origin')
};
const ACUERDO_PAIS = [
  [['guatemala','honduras','nicaragua','costa rica','el salvador'], 'mcca'],
  [['estados unidos','usa','eeuu','republica dominicana'], 'cafta'],
  [['mexico'], 'mexico'], [['panama'], 'panama'],
  [['colombia','chile','taiwan','corea del sur','corea'], 'tlc'],
  [['eslovenia','italia','portugal','espana','alemania','francia','rumania','polonia','union europea'], 'ue'],
  [['reino unido'], 'uk']
];
function acuerdoBase(o){
  const n = norm(o).trim(); if (!n) return '';
  for (const [ps, k] of ACUERDO_PAIS) if (ps.some(p=>n === p || n.includes(p))) return k;
  return '';
}
function notaOrigen(o, paises){
  const n = norm(o).trim();
  if (!n) return '';
  const cat = (paises || []).find(p=>norm(p.nombre).trim() === n);
  if (cat){ const t = ACUERDO_TXT[cat.acuerdo] || ''; return [t, cat.nota].filter(Boolean).join('. '); }
  return ACUERDO_TXT[acuerdoBase(o)] || '';
}
/* Dígitos del código nacional de cada país destino (los define la configuración; si no, los iniciales) */
function digitosPais(iso, ds){
  const d = (ds || DESTINOS_BASE).find(x=>x.iso === iso) || DESTINOS_BASE.find(x=>x.iso === iso);
  return d ? limDig(d.digitos, 10) : 10;
}
/* Muestra el código con los dígitos que usa el país: corta lo que sobra y marca con _ lo que falta */
function fmtPais(cod, n){
  const d = digits(cod); if (!d) return '';
  const len = n || d.length;
  const s = (d + '_'.repeat(Math.max(0, len - d.length))).slice(0, len);
  let o = s.slice(0, 4) + '.' + s.slice(4, 6);
  for (let i = 6; i < s.length; i += 2) o += '.' + s.slice(i, i + 2);
  return o;
}
const ESTADOS = {borrador:tr('Draft'), sugerida:tr('Draft · complete'), revision:tr('In review'), aprobado:tr('Approved'), corregido:tr('Corrected')};
const ESTADO_COLOR = {borrador:'#94A3B8', sugerida:'#D69E2E', revision:'#1D5FB0', aprobado:'#2F855A', corregido:'#4636A6'};
const EDAD_LBL = {adulto:'adult', nino:tr('child or youth'), bebe:'baby', general:tr('child, youth or adult')};

/* ---------- Consistencia: incoherencias y verificación del código ---------- */
const CAP_OK = {prenda:['61','62','42','39','65'], calzado:['64'], plantilla:['64'], polainas:['64'], cordones:['63','64','39','42'], cuidado_calzado:['34','38','96'],
  bolso:['42','63'], gorra:['65'], cinturon:['42','61','62','39'], lentes_sol:['90'], sombrilla:['66'], botella:['96','73','76','39','70'], llavero:['73','71','42','63','39','83'], reloj:['91','85'],
  tienda:['63'], saco:['94'], colchoneta:['94','63','39','40'], manta:['63'], toalla:['63'], mueble_camping:['94'], linterna:['85'], bastones:['66','95'], equipo_deporte:['95','94','40','39'], magnesio:['28','38'], patineta:['95'],
  bisuteria:['71','42','63','39'], avios:['96','83','39'], accesorio_pelo:['96','61','62','40'], correa_reloj:['91'], peleteria:['43'], hamaca:['56','63'], parche:['49','58','39','40'], mascota:['42'], bolsa_compra:['48','39','42','63'], caja:['48','39'], gancho:['39','73','44'], etiqueta:['48','58','39'], exhibidor:['94','96','73','76']};
function capsOk(t){ return CAP_OK[t] || CAP_OK[grupoTipo(t)] || null; }
function implicaciones(c6){
  const I = {}; const h = c6.slice(0,4), ch = c6.slice(0,2);
  if (ch === '61') I.tejido = 'punto';
  if (ch === '62' && h !== '6212') I.tejido = 'plano';
  if (h === '6111' || h === '6209') I.bebe = true;
  if (['6101','6103','6105','6107','6201','6203','6205','6207'].includes(h) || ['621132','621133','621139','611231','611239','621111','621020','621040'].includes(c6)) I.genero = 'M';
  if (['6102','6104','6106','6108','6202','6204','6206','6208'].includes(h) || ['621142','621143','621149','611241','611249','621112','621030','621050'].includes(c6)) I.genero = 'F';
  if (h === '6113' || h === '6210') I.recubierta = true;
  const ds = norm(DESC[c6] || '');
  if (/de algodon\)?$/.test(ds)) I.fibra = 'algodon';
  else if (/de fibras sinteticas o artificiales\)?$/.test(ds)) I.fibra = 'manmade';
  else if (/de fibras sinteticas\)?$/.test(ds)) I.fibra = 'sintetica';
  else if (/de fibras artificiales\)?$/.test(ds)) I.fibra = 'artificial';
  else if (/de lana( o pelo fino)?\)?$/.test(ds)) I.fibra = 'lana';
  else if (/de seda\)?$/.test(ds)) I.fibra = 'seda';
  if (h === '6401'){ I.upper = 'plastico'; I.sole = 'caucho'; I.impermeable = true; }
  if (h === '6402'){ I.upper = 'plastico'; I.sole = 'caucho'; }
  if (h === '6403'){ I.upper = 'cuero'; if (['640320','640351','640359'].includes(c6)) I.sole = 'cuero'; if (['640391','640399'].includes(c6)) I.sole = 'caucho'; }
  if (c6 === '640411' || c6 === '640419'){ I.upper = 'textil'; I.sole = 'caucho'; }
  if (c6 === '640420'){ I.upper = 'textil'; I.sole = 'cuero'; }
  if (c6 === '640510') I.upper = 'cuero';
  if (c6 === '640520') I.upper = 'textil';
  if (['640192','640291','640351','640391'].includes(c6)) I.tob = true;
  if (['640299','640359','640399'].includes(c6)) I.tob = false;
  if (['640110','640340'].includes(c6)) I.metal = true;
  if (c6 === '640220') I.tetones = true;
  if (c6 === '640212' || c6 === '640312') I.esqui = true;
  if (h === '4202'){ const x = c6[5]; I.exterior = x === '1' ? 'cuero' : x === '2' ? 'textil' : 'otro'; }
  return I;
}
function verificarCodigo(f, cod){
  const A = [], t = f.tipo;
  if (!t || cod.length < 4) return A;
  const E = m => A.push({nivel:'error', origen:'codigo', msg:m}), W = m => A.push({nivel:'aviso', origen:'codigo', msg:m});
  const ch = cod.slice(0,2), c6 = cod.slice(0,6), cd = fmtCode(c6);
  const oks = capsOk(t);
  if (oks && !oks.includes(ch)){ E(tr('Code {0} is in chapter {1}{2}, which does not match "{3}".', [fmtCode(cod), ch, CAPITULOS[ch] ? ' (' + CAPITULOS[ch] + ')' : '', TIPO_CORTO[t]])); return A; }
  if (c6.length < 6) return A;
  if (!DESC[c6]) W(tr('Subheading {0} is not in the classifier\'s reference table; confirm it in the tariff.', [cd]));
  const I = implicaciones(c6), g = grupoTipo(t);
  if (g === 'prenda' || ['manta','tienda','cinturon'].includes(t)){
    if (I.tejido && f.tejido && t !== 'calcetines' && I.tejido !== f.tejido) E(tr('{0} is {1}, but the item is marked as {2}', [cd, I.tejido === 'punto' ? tr('knitted (chapter 61)') : tr('woven (chapter 62)'), f.tejido === 'punto' ? 'knitted.' : 'woven.']));
    if (I.genero && ['M','F'].includes(f.genero) && I.genero !== f.genero) E(tr('{0} is for {1}, but the item is for {2}', [cd, I.genero === 'M' ? tr('men or boys') : tr('women or girls'), f.genero === 'M' ? tr('men or boys.') : tr('women or girls.')]));
    if (I.genero === 'M' && f.genero === 'U') W(tr('Unisex is classified as women\'s; {0} is men\'s.', [cd]));
    if (I.bebe && f.edad && f.edad !== 'bebe') E(tr('{0} is for baby garments (up to 86 cm), but the age is {1}.', [cd, EDAD_LBL[f.edad]]));
    if (!I.bebe && f.edad === 'bebe' && (ch === '61' || ch === '62') && c6.slice(0,4) !== '6212') E(tr('Baby garments go in 6111 or 6209; {0} does not apply.', [cd]));
    const comp = parseComp((f.comp || {}).exterior || f.composicion || '');
    if (I.fibra && comp && comp.pred && comp.pred.grupo !== 'cuero'){
      const p = comp.pred, ok = I.fibra === 'manmade' ? p.familia === 'manmade' : p.grupo === I.fibra;
      if (!ok) E(tr('{0} is for {1}, but the outer fabric is predominantly {2} ({3}%).', [cd, OPT_LBL[I.fibra], FIB_LBL[p.grupo], p.pct]));
    }
    if (I.recubierta && f.recubierta === false && ATTR_BY.recubierta.aplica(f)) W(tr('{0} is for coated or laminated fabrics; the item is not marked that way.', [cd]));
    if (!I.recubierta && f.recubierta && (ch === '61' || ch === '62') && f.edad !== 'bebe') W(tr('The fabric is marked as coated or laminated; it would normally go in 6113 or 6210.'));
  }
  if (t === 'calzado'){
    const dv = derivarCalzado(f);
    if (I.upper && dv.upper && I.upper !== dv.upper) E(tr('{0} is for an upper of {1}, but the upper is {2}.', [cd, MAT_LBL[I.upper], MAT_LBL[dv.upper]]));
    if (I.sole && dv.sole && I.sole !== dv.sole) E(tr('{0} is for a sole of {1}, but the sole is {2}.', [cd, MAT_LBL[I.sole], MAT_LBL[dv.sole]]));
    if (I.tob !== undefined && f.altura){ const tob = f.altura !== 'bajo'; if (I.tob !== tob) E(I.tob ? (tob ? tr('{0} is for footwear covering the ankle, and the item covers it.', [cd]) : tr('{0} is for footwear covering the ankle, but the item does not cover it.', [cd])) : (tob ? tr('{0} is for footwear not covering the ankle, but the item covers it.', [cd]) : tr('{0} is for footwear not covering the ankle, and the item does not cover it.', [cd]))); }
    if (c6 === '640192' && f.altura === 'rodilla') E(tr('6401.92 is for footwear covering the ankle but not the knee; if it covers the knee it goes in 6401.99.'));
    if (I.metal && f.puntera !== 'metalica') E(tr('{0} requires a metal protective toe cap.', [cd]));
    if (!I.metal && f.puntera === 'metalica' && dv.upper === 'cuero' && c6.startsWith('6403')) E(tr('With a leather upper and a metal toe cap, 6403.40 applies, not {0}.', [cd]));
    if (I.impermeable && !f.impermeable) W(tr('{0} is for waterproof footwear without stitches or rivets; the item is not marked that way.', [cd]));
    if (I.tetones && f.estiloCalz !== 'chancla_tetones') W(tr('6402.20 is for straps attached to the sole by plugs; the chosen style is different.'));
    if (I.esqui && f.estiloCalz !== 'esqui') W(tr('{0} is for ski or snowboard footwear.', [cd]));
    if (c6 === '640411' && f.estiloCalz && f.estiloCalz !== 'tenis' && f.estiloCalz !== 'tacos' && f.estiloCalz !== 'esqui') W(tr('6404.11 is for sports or training footwear; the chosen style is {0}.', [opcionLbl('estiloCalz', f.estiloCalz).toLowerCase()]));
    if (c6 === '640411' && f.estiloCalz === 'tenis' && f.disenio && f.disenio !== 'entrenamiento') W(tr('6404.11 is for athletic or training footwear; the design is set as {0}.', [opcionLbl('disenio', f.disenio).toLowerCase()]));
  }
  if (g === 'bolso' && I.exterior && f.exterior){
    const ok = I.exterior === 'textil' ? ['textil','plastico'].includes(f.exterior) : I.exterior === f.exterior;
    if (!ok) E(tr('{0} is for an outer surface of {1}, but the item has an outer surface of {2}.', [cd, ({cuero:'leather', textil:tr('textile material or plastic sheeting'), otro:tr('other material')})[I.exterior], opcionLbl('exterior', f.exterior).toLowerCase()]));
  }
  return A;
}
function segmentosComp(raw){
  return norm(raw).replace(RE_LABELS, '\n$1:').split(/[\n;|]+/).map(x=>x.trim()).filter(Boolean).map(p=>{ const m = p.match(/^([a-z][a-z ]{1,20}?)\s*:\s*(.*)$/); return m ? m[2] : p; });
}
function validar(f, ctx, codFinal){
  ctx = ctx || {};
  const A = [];
  const add = (nivel, msg, origen) => { if (!A.some(a=>a.msg === msg)) A.push({nivel, msg, origen: origen || 'datos'}); };
  const t = f.tipo, g = grupoTipo(t), desc = norm(textoDet(f));
  const partes = partesDe(t, f);
  for (const [p, v] of Object.entries(f.comp || {})){
    if (!String(v || '').trim() || (t && !partes.includes(p))) continue;
    const esMat = ['corte','suela','material'].includes(p) || ['bolso','gorra'].includes(grupoTipo(t));
    const pr = prepMat(v);
    segmentosComp(v).forEach(seg=>{
      const pcts = [...seg.matchAll(/(\d+(?:[.,]\d+)?)\s*%/g)].map(m=>parseFloat(m[1].replace(',','.')));
      if (pcts.length){
        const sum = Math.round(pcts.reduce((a,b)=>a+b,0)*10)/10;
        if (sum > 100.5) add('error', tr('{0}: the percentages add up to {1}%.', [PARTE_LBL[p], sum]));
        else if (sum < 99.5) add('aviso', tr('{0}: the percentages add up to {1}%, not 100%.', [PARTE_LBL[p], sum]));
      }
      if (!['relleno','plantilla'].includes(p)){
        const o2 = pesosDe(seg, MAT_CALZ).otra || 0, otra = esMat ? o2 : Math.min(pesosDe(seg, FIBRAS).otra || 0, o2);
        if (otra && !pr.desconocidas.length) add('aviso', tr('{0}: {1}% has no recognizable material.', [PARTE_LBL[p], otra]));
      }
    });
    if (!['relleno','plantilla'].includes(p) && pr.desconocidas.length) add('aviso', tr('{0}: I do not recognize "{1}". Tell me what it is with the list under the composition.', [PARTE_LBL[p], pr.desconocidas.join('", "')]), 'material');
    pr.ambiguas.forEach(w=>add('aviso', PARTE_LBL[p] + ': ' + MAT_AMBIGUAS[w] + '.'));
    const fz = pr.cambios.filter(c=>c.de && !c.aprendido);
    if (fz.length) add('info', tr('{0}: I read {1}.', [PARTE_LBL[p], fz.map(c=>tr('"{0}" as {1}', [c.de, c.a])).join(', ')]));
    if (pr.cambios.some(c=>c.pct)) add('info', tr('{0}: numbers without % were taken as percentages ({1}).', [PARTE_LBL[p], pr.s.trim()]));
    if (['corte','exterior','material'].includes(p) && esMat){
      const pm = parseMat(v, 'corte');
      if (pm && pm.mixto && !pm.pred) add('aviso', tr('{0}: mixes {1} without percentages. Enter them by surface to know which governs.', [PARTE_LBL[p], pm.grupos.map(g=>MAT_LBL[g]).join(' y ')]));
    }
  }
  const prep0 = prepararEstado(Object.assign({}, f));
  for (const a of ATTRS){
    if (!a.deComp || !a.aplica(prep0) || !f[a.id]) continue;
    const fx = a.fijo(f);
    if (fx && fx !== f[a.id]) add('error', tr('{0} recorded as "{1}", but the composition says {2}. It is classified by the composition; fix whichever is wrong.', [a.label, opcionLbl(a.id, f[a.id]), opcionLbl(a.id, fx).toLowerCase()]));
  }
  if (t === 'calzado'){
    const pmC = parseMat((f.comp || {}).corte || '', 'corte');
    if (pmC && pmC.pred){
      const p = pmC.pesos;
      const dTex = /\b(canvas|lona|mesh|malla|knit|textile|textil|nylon|ripstop|corduroy|pana|denim|jersey)\b/.test(desc);
      const dCue = /\b(leather|cuero|suede|gamuza|nubuck|piel)\b/.test(desc) && !/\b(synthetic|sintetic[oa]|faux|vegan)\b/.test(desc);
      if (dTex && !(p.textil > 0)) add('aviso', tr('The description mentions canvas, mesh or textile, but the upper composition has no textile. Check the composition by surface.'));
      if (dCue && !(p.cuero > 0)) add('aviso', tr('The description mentions leather or suede, but the upper composition does not include it.'));
      if (Object.keys(p).filter(k=>k !== 'otra').length === 1 && pmC.pct === 100 && pmC.pred === 'cuero' && /\b(old skool|sk8|authentic|era|slip-?on|chuck|canvas)\b/.test(desc)) add('aviso', tr('This model usually combines suede or leather with canvas; confirm the upper is 100% leather.'));
    } else if (!(f.comp || {}).corte) add('aviso', tr('The upper composition is missing: without it the governing material of the footwear cannot be verified.'));
    if (!(f.comp || {}).suela) add('info', tr('The sole composition is missing.'));
  }
  if (grupoTipo(t) === 'prenda' && t !== 'brasier' && !(f.comp || {}).exterior) add('aviso', tr('The outer fabric composition is missing: the subheading depends on the predominant fiber.'));
  if (grupoTipo(t) === 'bolso' && !(f.comp || {}).exterior && !f.exterior) add('info', tr('The outer surface material is missing.'));
  if (f.uso && t){
    const du = detectar(f.uso, {}).tipo;
    if (du && grupoTipo(du) !== grupoTipo(t) && !['bolso_viaje','bolsa_compra'].includes(du)) add('info', tr('In "what it is for" you describe something that looks like "{0}"; the chosen type is "{1}".', [TIPO_CORTO[du], TIPO_CORTO[t]]));
  }
  if (ctx.porEstilo && (f.estilo || f.generico)){
    const vistos = new Set();
    const otros = [].concat(f.estilo ? (ctx.porEstilo.get(norm(f.estilo).trim()) || []) : [], f.generico && ctx.porGenerico ? (ctx.porGenerico.get(norm(f.generico).trim()) || []) : []).filter(r=>r.id !== f.id && !vistos.has(r.id) && vistos.add(r.id));
    const c6 = digits(codFinal).slice(0,6);
    const difC = c6.length === 6 ? otros.find(r=>digits(r.codigo).length >= 6 && digits(r.codigo).slice(0,6) !== c6) : null;
    if (difC) add('aviso', tr('The same {0} is already classified as {1}{2}. Colors of one style usually share the same code; check which is right.', [f.estilo ? tr('style {0}', [f.estilo]) : tr('generic code {0}', [f.generico]), fmtCode(difC.codigo), difC.color ? tr(' (color {0})', [difC.color]) : '']), 'codigo');
    const difT = otros.find(r=>r.tipo && t && r.tipo !== t);
    if (difT) add('aviso', tr('The {0} is recorded in another product as "{1}".', [f.estilo ? tr('style {0}', [f.estilo]) : tr('generic code {0}', [f.generico]), TIPO_CORTO[difT.tipo]]));
    if (t === 'calzado'){
      const mio = parseMat((f.comp || {}).corte || '', 'corte');
      const otro = otros.map(r=>({r, pm:parseMat((r.comp || {}).corte || '', 'corte')})).find(x=>x.pm && x.pm.pred && mio && mio.pred && x.pm.pred !== mio.pred);
      if (otro) add('aviso', tr('Another color of the same style ({0}) has an upper of {1} ({2}); this one says {3}.', [otro.r.color || otro.r.id, MAT_LBL[otro.pm.pred], resumenMat(otro.pm), MAT_LBL[mio.pred]]));
    }
  }
  const comp = parseComp((f.comp || {}).exterior || f.composicion || '');
  if (comp && comp.pred && comp.pred.grupo === 'cuero' && ['camiseta','calcetines','traje_bano','ropa_interior','brasier','bufanda'].includes(t)) add('error', tr('The outer fabric says leather, very unusual for {0}. Check the composition or the type.', [TIPO_CORTO[t].toLowerCase()]));
  if (t === 'calzado' && (f.comp || {}).exterior && !(f.comp || {}).corte) add('info', tr('For footwear, the composition goes by part: upper and sole.'));
  if (textoDet(f)){
    const d = detectarCon(textoDet(f), {}, '', ctx.palabras, f.marca);
    if (d.tipo && t && grupoTipo(d.tipo) !== grupoTipo(t) && !(d.tipo === 'bolso_viaje' && !/\b(duffel|duffle|belt ?bag|lonchera|lunch)\b/.test(desc))) add('aviso', tr('The style looks like "{0}", but the chosen type is "{1}".', [TIPO_CORTO[d.tipo], TIPO_CORTO[t]]));
    const prep = prepararEstado(Object.assign({}, f));
    for (const a of ATTRS){
      if (a.tipo === 'check' || !a.aplica(prep) || d[a.id] == null || d[a.id] === '' || f[a.id] === d[a.id]) continue;
      const op = a.ops.find(o=>o.v === d[a.id]);
      const r = op && op.off ? op.off(prep) : null;
      if (r) add('aviso', tr('The style suggests "{0}" ({1}), but it does not fit: {2}{3}', [op.l.toLowerCase(), a.label.toLowerCase(), r.charAt(0).toLowerCase(), r.slice(1)]));
    }
    const gd = parseGenero(textoDet(f));
    if (['M','F'].includes(gd) && ['M','F'].includes(f.genero) && gd !== f.genero && ATTR_BY.genero.aplica(f) && !ATTR_BY.genero.fijo(f)) add('aviso', tr('The style indicates {0}, but the chosen gender is {1}', [gd === 'M' ? 'hombre' : 'mujer', f.genero === 'M' ? 'hombre.' : 'mujer.']));
    const ed = parseEdad(textoDet(f));
    if (ATTR_BY.edad.aplica(f) && f.edad && ((ed === 'bebe') !== (f.edad === 'bebe')) && (ed === 'bebe' || f.edad === 'bebe')) add('aviso', ed === 'bebe' ? tr('The description suggests a baby garment, but it is not marked that way.') : tr('It is marked as a baby garment, but the description does not suggest it.'));
    if (t === 'calzado'){
      if (/\b(steel toe|punta de acero|safety toe|alloy toe|aluminum toe)\b/.test(desc) && f.puntera !== 'metalica') add('aviso', tr('The description mentions a steel or alloy toe, but the toe cap is not set as metal.'));
      if (/\b(composite|nano toe|carbon toe)\b/.test(desc) && f.puntera === 'metalica') add('aviso', tr('The description says composite, which is not a metal toe cap.'));
      if (/\b(hi|high|high-?top|mid|boots?|botas?)\b/.test(desc) && f.altura === 'bajo') add('aviso', tr('The description suggests a high cut (hi, mid or boot), but it is marked as not covering the ankle.'));
      if (/\b(low|lo)\b/.test(desc) && ['tobillo','rodilla'].includes(f.altura) && !/\b(mid|hi|high)\b/.test(desc)) add('aviso', tr('The description suggests a low model, but it is marked as covering the ankle.'));
      const dv = derivarCalzado(f);
      if (!(f.comp || {}).corte && dv.upper === 'textil' && /\b(leather|cuero|suede|gamuza|nubuck)\b/.test(desc) && !/\b(synthetic|sintetic[oa]|faux)\b/.test(desc)) add('aviso', tr('The description mentions leather but the upper is set as textile. If the upper is mixed, enter its percentages.'));
      if (/\b(waterproof|wp|gore-?tex|impermeable)\b/.test(desc) && dv.upper && dv.upper !== 'plastico') add('info', tr('Being waterproof through a membrane does not take it to 6401: that heading requires a rubber or plastic upper and sole without stitching.'));
      if (f.estiloCalz === 'tacon' && f.genero === 'M') add('aviso', tr('High-heeled shoe marked as men\'s; confirm the gender.'));
      if (f.estiloCalz === 'zueco' && f.impermeable) add('aviso', tr('A clog with ventilation holes is not waterproof; confirm before using 6401.'));
      if (f.estiloCalz === 'seguridad' && dv.upper && !['cuero','plastico','textil'].includes(dv.upper)) add('aviso', tr('Safety footwear with an upper of another material: check the upper composition.'));
    }
    if (g === 'prenda'){
      if (/\b(fleece|polar|jersey|knit|pique|terry)\b/.test(desc) && f.tejido === 'plano') add('aviso', tr('The description mentions a knit fabric (fleece, jersey, knit), but it is marked as woven.'));
      if (/\b(denim|jeans?|flannel|franela|poplin|twill|canvas|ripstop|oxford)\b/.test(desc) && f.tejido === 'punto') add('aviso', tr('The description mentions a woven fabric (denim, flannel, ripstop), but it is marked as knitted.'));
      const hay = desc + ' ' + norm(Object.values(f.comp || {}).join(' '));
      if (f.recubierta && !/\b(dryvent|dry vent|gore|futurelight|waterproof|laminad[oa]|laminated|coated|recubiert[oa]|hyvent|pu|pvc|impermeable|rain)\b/.test(hay)) add('info', tr('You marked the fabric as coated but it is not in the description or the composition; confirm it with the technical sheet.'));
      if (t === 'chaqueta' && f.hechura === 'chaqueta' && /\b(vests?|chalecos?|gilet)\b/.test(desc)) add('aviso', tr('The description says vest, but the construction is set as jacket.'));
      if (t === 'sudadera' && f.hechuraSud === 'pullover' && /\b(full ?zip|fz|cierre completo)\b/.test(desc)) add('aviso', tr('The description says full zip, but the construction is set as pullover.'));
      if (t === 'traje_bano' && f.edad === 'adulto' && /\b(baby|bebe|infant)\b/.test(desc)) add('aviso', tr('Swimsuit with a baby description; check the age.'));
    }
    if (t === 'botella' && /\b(vacuum|al vacio|termo|thermos|insulated)\b/.test(desc) && !f.alVacio) add('aviso', tr('The description says thermos or vacuum, but vacuum insulation is not checked.'));
    if (t === 'reloj' && /\b(smart|gps|bluetooth)\b/.test(desc) && f.pantalla && f.pantalla !== 'inteligente') add('aviso', tr('The description suggests a smartwatch.'));
    if (t === 'colchoneta' && /\b(self-?inflating|autoinflable)\b/.test(desc) && f.tipoColch === 'inflable') add('info', tr('Self-inflating pads contain foam; check whether the foam option applies.'));
  }
  if (f.tallas && ATTR_BY.edad.aplica(f)){
    const et = parseTallas(f.tallas);
    if (et && f.edad && et !== f.edad && (et === 'bebe' || f.edad === 'bebe' || (et === 'nino' && f.edad === 'adulto'))) add('aviso', tr('The sizes ({0}) do not match the chosen age ({1}).', [f.tallas, EDAD_LBL[f.edad]]));
    if (et === 'bebe' && !f.edad) add('aviso', tr('The sizes are baby sizes: mark the age as baby, because it changes the code.'));
  }
  if (ctx.marcas && f.marca){
    const m = ctx.marcas.find(x=>norm(x.nombre).trim() === norm(f.marca).trim());
    if (m){
      if (m.activa === false) add('info', tr('Brand {0} is marked as inactive.', [m.nombre]));
      if (t && Array.isArray(m.tipos) && m.tipos.length && !m.tipos.includes(t)) add('aviso', tr('{0} does not have "{1}" among its product types.', [m.nombre, TIPO_CORTO[t]]));
    } else if (ctx.marcas.length) add('info', tr('Brand "{0}" is not in the catalog.', [f.marca]));
  }
  if (ctx.proveedores && f.proveedor && f.marca){
    const p = ctx.proveedores.find(x=>norm(x.nombre).trim() === norm(f.proveedor).trim());
    if (p && Array.isArray(p.marcas) && p.marcas.length && !p.marcas.some(x=>norm(x).trim() === norm(f.marca).trim())) add('aviso', tr('Supplier {0} does not have the brand {1}.', [p.nombre, f.marca]));
  }
  const cod = digits(codFinal);
  if (cod) verificarCodigo(f, cod).forEach(a=>add(a.nivel, a.msg, 'codigo'));
  return A;
}
function alertaKey(msg){ let h = 5381; const t = String(msg); for (let i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) >>> 0; return h.toString(36); }
function alertasVivas(al, ok){ const s = new Set(ok || []); return al.filter(a=>a.nivel === 'error' || !s.has(alertaKey(a.msg))); }
function evaluar(f, recs, incisos, ctx, codFinal, excluirId){
  const o = sugerir(f, recs, incisos, excluirId, ctx);
  o.alertas = validar(f, ctx, codFinal);
  const datos = alertasVivas(o.alertas, f.alertasOk).filter(a=>a.origen !== 'codigo');
  if (datos.some(a=>a.nivel === 'error')) o.conf = Math.min(o.conf, 1);
  else if (datos.some(a=>a.nivel === 'aviso')) o.conf = Math.min(o.conf, 2);
  o.confianza = [tr('no data'),'low','medium','high'][o.conf];
  return o;
}

/* ---------- Códigos nacionales por país destino ----------
   Los incisos nacionales (8 a 12 dígitos) vienen de la base de datos: base cargada,
   aprendidos al confirmar un código o escritos a mano. Cada uno puede tener
   condiciones (género, edad, estilo de calzado, valor CIF…). */
const vacio = v => v === undefined || v === null || v === '';
function incisosDe(iso, sub6, incisos, ds){
  const out = [];
  (incisos || []).forEach(x=>{ if (x.pais === iso && digits(x.codigo).startsWith(sub6)) out.push({codigo:digits(x.codigo), desc:x.descripcion || descDe(x.codigo), dai:x.dai, nota:x.nota, fuente:x.fuente || 'manual', cond:x.cond || null, prio:x.prio || 0, id:x.id}); });
  const res = recortarIncisos(out, digitosPais(iso, ds));
  return res.filter(x=>x.cond || !res.some(y=>y !== x && y.codigo.length > x.codigo.length && y.codigo.startsWith(x.codigo))).sort((a,b)=>a.codigo.localeCompare(b.codigo));
}
/* Lleva los incisos a los dígitos del país. Los más largos se cortan; si varios quedan iguales se juntan. */
function recortarIncisos(lista, n){
  const res = [], grupos = new Map();
  lista.forEach(o=>{ if (o.codigo.length > n){ const c = o.codigo.slice(0, n); if (!grupos.has(c)) grupos.set(c, []); grupos.get(c).push(o); } else res.push(o); });
  grupos.forEach((ms, c)=>{
    const daiS = [...new Set(ms.map(m=>vacio(m.dai) ? '' : String(m.dai)).filter(Boolean))];
    const exactos = res.filter(o=>o.codigo === c);
    if (exactos.length){ exactos.forEach(e=>{ if (vacio(e.dai) && daiS.length === 1) e.dai = daiS[0]; }); return; }
    const conds = [...new Set(ms.map(m=>m.cond ? JSON.stringify(m.cond) : ''))];
    const fte = ms.some(m=>m.fuente === 'arancel') ? 'arancel' : ms[0].fuente;
    res.push({codigo:c, desc:(ms.length === 1 ? ms[0].desc : tr('{0} (merges {1} longer codes)', [descDe(c), ms.length])) + (daiS.length > 1 ? tr('. Duty varies: {0}%', [daiS.join('%, ')]) : ''),
      dai:daiS.length === 1 ? daiS[0] : '', daiVaria:daiS.length > 1 ? daiS : null, fuente:fte,
      cond:conds.length === 1 && conds[0] ? ms[0].cond : {}, prio:Math.max(0, ...ms.map(m=>m.prio || 0)), id:ms[0].id, recorte:ms.map(m=>m.codigo)});
  });
  return res;
}
/* Inciso único por subpartida del país base (para completar la sugerida a todos sus dígitos) */
function incisosBase(incisos, iso, ds){
  const m = {}, subs = new Set();
  (incisos || []).forEach(x=>{ if (x.pais === iso) subs.add(digits(x.codigo).slice(0,6)); });
  subs.forEach(sub=>{ const l = incisosDe(iso, sub, incisos, ds); if (l.length === 1) m[sub] = {inciso:l[0].codigo, dai:l[0].dai, nota:l[0].nota}; });
  return m;
}
const RE_DEMAS = /^(los|las) dem[a]s\b|^otros?\b|^otras?\b|^los demas\b|^las demas\b/;
function normDesc(d){ return norm(d).replace(/^[\s\-–—.:]+/, '').replace(/\s+/g, ' ').trim(); }
function cifRango(d){
  const m = d.match(/valor cif (inferior o igual|superior|inferior|mayor|menor)[^0-9]*([\d.,]+)/);
  if (!m) return null;
  const v = parseFloat(m[2].replace(/\.(?=\d{3}\b)/g, '').replace(',', '.'));
  return {op: /inferior|menor/.test(m[1]) ? 'le' : 'gt', val:v};
}
/* Datos que piden los aranceles nacionales (solo se preguntan si el arancel del país los usa) */
const NAC_PREG = [
  {id:'valorCIF', label:tr('CIF value per pair or unit (US$)'), tipo:'num'},
  {id:'genero', label:tr('Gender'), tipo:'attr'},
  {id:'edadNac', label:tr('User age'), tipo:'seg', ops:[['adulto',tr('Adult')],['nino',tr('Child')],['bebe',tr('Infant or baby')]]},
  {id:'usoPrevisto', label:tr('Use'), tipo:'seg', ops:[['casual',tr('Casual or everyday')],['escolar',tr('School or uniform')],['deportivo',tr('Sports')],['trabajo',tr('Work or industrial')]]},
  {id:'largo', label:tr('Length'), tipo:'seg', ops:[['largo',tr('Long')],['corto',tr('Short (shorts or bermudas)')]]},
  {id:'peto', label:tr('With bib (overalls)'), tipo:'sino'},
  {id:'mezclilla', label:tr('Denim fabric'), tipo:'sino'},
  {id:'suelaEspumosa', label:tr('Sole of foam or cellular material (EVA, foam)'), tipo:'sino'},
  {id:'rodeaDedo', label:tr('Straps over the instep that go around the big toe'), tipo:'sino'},
  {id:'manga', label:tr('Sleeve'), tipo:'attr'},
  {id:'conCuello', label:tr('With collar'), tipo:'sino'},
  {id:'capucha', label:tr('With hood'), tipo:'sino'},
  {id:'sueter', label:tr('It is a sweater (jersey), not a sweatshirt'), tipo:'sino'},
  {id:'formaTocado', label:tr('Shape'), tipo:'seg', ops:[['gorra',tr('Cap with visor')],['gorro',tr('Beanie')],['sombrero',tr('Hat (with brim)')],['otro',tr('Other')]]},
  {id:'claseBolso', label:tr('Bag class'), tipo:'seg', ops:[['mochila',tr('Backpack')],['cangurera',tr('Waist pack')],['duffel',tr('Duffel or travel bag')],['deporte',tr('Sports bag')],['termico',tr('Cooler or lunch bag')],['neceser',tr('Toiletry bag')],['bolso_mano',tr('Handbag')],['crossbody',tr('Crossbody')],['tote',tr('Tote')],['satchel',tr('Satchel')],['cartera',tr('Purse')],['otro',tr('Other')]]}
];
const NAC_IDS = NAC_PREG.filter(q=>q.tipo !== 'attr').map(q=>q.id);
function detectarNac(f, soloVacios){
  const t = norm([textoDet(f), f.uso].join(' ')), c = norm(Object.values(f.comp || {}).join(' '));
  const pon = (k, v) => { if (!soloVacios || vacio(f[k])) f[k] = v; };
  if (/\b(escolar|school|uniforme)\b/.test(t)) pon('usoPrevisto', 'escolar');
  else if (/\b(work|trabajo|industrial|safety|seguridad)\b/.test(t)) pon('usoPrevisto', 'trabajo');
  if (/\b(denim|jeans?|mezclilla)\b/.test(t + ' ' + c)) pon('mezclilla', true);
  if (f.tipo === 'pantalon'){ if (/\b(shorts?|bermudas?|short)\b/.test(t)) pon('largo', 'corto'); else if (/\b(pants?|pantalon(es)?|jeans?|joggers?|trousers?|leggings?|chinos?)\b/.test(t)) pon('largo', 'largo'); if (/\b(overall|overol|bib)\b/.test(t)) pon('peto', true); }
  if (f.tipo === 'calzado' && (f.comp || {}).suela){ if (/\b(eva|phylon|md|foam|espuma|espumos)/.test(norm(f.comp.suela))) pon('suelaEspumosa', true); else if (/\b(caucho|rubber|goma|cuero|leather|tpr|tpu|pvc)\b/.test(norm(f.comp.suela))) pon('suelaEspumosa', false); }
  if (/\b(bebes?|baby|infante|infant|toddler|primera infancia)\b/.test(t)) pon('edadNac', 'bebe');
  else if (/\b(ninos?|ninas?|kids?|youth|boys?|girls?|juvenil|infantil|escolar)\b/.test(t)) pon('edadNac', 'nino');
  else if (/\b(hombres?|mujer(es)?|damas?|caballeros?|mens?|womens?|ladies|adultos?)\b/.test(t)) pon('edadNac', 'adulto');
  else if (f.tipo === 'calzado' && ['seguridad','tacon'].includes(f.estiloCalz)) pon('edadNac', 'adulto');
  if (/\b(hood|hooded|hoodie|capucha)\b/.test(t)) pon('capucha', true);
  if (f.tipo === 'sudadera'){ if (/\b(sweaters?|sueter(es)?|jerseys?|cardigans?|knit sweater)\b/.test(t)) pon('sueter', true); else if (/\b(hoodie|sudadera|sweatshirt|crew|fleece|pullover|pulover)\b/.test(t)) pon('sueter', false); }
  if (f.tipo === 'gorra'){ if (/\b(hats?|sombrero|bucket|boonie|fedora|panama|sun hat)\b/.test(t)) pon('formaTocado', 'sombrero'); else if (/\b(beanie|gorro|toque|knit cap)\b/.test(t)) pon('formaTocado', 'gorro'); else if (/\b(caps?|gorra|trucker|snapback|visera)\b/.test(t)) pon('formaTocado', 'gorra'); }
  if (['mochila','bolso_viaje','bolso_mano','billetera','maleta'].includes(f.tipo)){
    const CB = [['cangurera', /\b(cangurera|rinonera|fanny|waist ?pack|belt bag|hip pack|bum bag)\b/], ['termico', /\b(termic[oa]|cooler|lonchera|lunch|insulated)\b/], ['duffel', /\b(duffel|duffle|bolso de viaje|travel bag|weekender)\b/],
      ['deporte', /\b(deporte|gym bag|sports? bag|bolsa para articulos de deporte)\b/], ['neceser', /\b(neceser|toiletry|dopp|cosmetic bag)\b/], ['crossbody', /\b(crossbody|cross body|bandolera)\b/], ['tote', /\b(tote)\b/],
      ['satchel', /\b(satchel)\b/], ['bolso_mano', /\b(bolso de mano|handbag)\b/], ['cartera', /\b(cartera|clutch|purse)\b/], ['mochila', /\b(mochila|backpack|daypack|rucksack|morral|sling)\b/]];
    const x = CB.find(([, re])=>re.test(t)); if (x) pon('claseBolso', x[0]); else if (f.tipo === 'mochila') pon('claseBolso', 'mochila');
  }
  if (/\b(polo|collar|cuello)\b/.test(t)) pon('conCuello', true);
  return f;
}
/* Puntúa un inciso nacional según su texto (en español, como lo publica cada arancel) */
function evaluarOpcion(d, f){
  const txt = norm([textoDet(f), f.uso, Object.values(f.comp || {}).join(' ')].join(' '));
  let sc = 0; const mal = [], faltan = [];
  const si = (cond, puntos, id) => { if (cond === true) sc += puntos; else if (cond === false) mal.push(id); else faltan.push(id); };
  const edad = edadDe(f), gen = f.genero;
  const deHombre = /\b(para|de) hombres?\b|\bmasculin/.test(d), deDama = /\b(para|de) (damas|mujeres?)\b|\bfemenin/.test(d);
  const deNino = /\bninos?\b|\bninas?\b|\binfantil|\bjuvenil/.test(d), deBebe = /primera infancia|\bbebes?\b|lactantes?/.test(d);
  if (deBebe) si(vacio(edad) ? undefined : edad === 'bebe', 3, 'edadNac');
  if (deNino && !deBebe) si(vacio(edad) ? undefined : edad === 'nino', 3, 'edadNac');
  if (deHombre) si(edad && edad !== 'adulto' ? false : (vacio(gen) ? undefined : (gen === 'M' ? (vacio(edad) ? undefined : true) : false)), 3, vacio(gen) ? 'genero' : 'edadNac');
  if (deDama) si(edad && edad !== 'adulto' ? false : (vacio(gen) ? undefined : (gen !== 'M' ? (vacio(edad) ? undefined : true) : false)), 3, vacio(gen) ? 'genero' : 'edadNac');
  if (f.tipo === 'calzado'){
    if (/calzados? de casa|pantuflas?/.test(d)) si(f.estiloCalz === 'pantufla', 10, 'casa');
    if (/deportes?|danzas?|deportiv/.test(d)) si(f.estiloCalz === 'tacos' || f.estiloCalz === 'esqui' || f.estiloCalz === 'danza' || (f.estiloCalz === 'tenis' && f.disenio === 'entrenamiento'), 10, 'deporte');
    if (/cubrecalzado|cubre calzado/.test(d)) si(f.estiloCalz === 'cubrecalzado', 10, 'cubrecalzado');
    if (/espumos|celular/.test(d)) si(vacio(f.suelaEspumosa) ? undefined : !!f.suelaEspumosa, 5, 'suelaEspumosa');
    if (/rodean? el dedo gordo/.test(d)) si(f.estiloCalz === 'chancla_tetones' ? true : (f.estiloCalz === 'sandalia' ? (vacio(f.rodeaDedo) ? undefined : !!f.rodeaDedo) : false), 5, 'rodeaDedo');
  } else if (/deportiv|\bdeportes?\b/.test(d)) si(vacio(f.usoPrevisto) ? undefined : f.usoPrevisto === 'deportivo', 10, 'usoPrevisto');
  if (/puntera metalica/.test(d)) si(f.puntera === 'metalica', 10, 'puntera');
  if (/cubran? la rodilla/.test(d)) si(f.altura === 'rodilla', 2, 'rodilla');
  else if (/cubran? el tobillo/.test(d)) si(vacio(f.altura) ? undefined : f.altura !== 'bajo', 2, 'altura');
  if (/escolar|uniforme/.test(d)) si(/escolar|school|uniforme/.test(txt) ? true : (vacio(f.usoPrevisto) ? undefined : f.usoPrevisto === 'escolar'), 10, 'usoPrevisto');
  if (/de trabajo|industrial/.test(d)) si(f.estiloCalz === 'seguridad' ? true : (vacio(f.usoPrevisto) ? undefined : f.usoPrevisto === 'trabajo'), 10, 'usoPrevisto');
  if (/mezclilla|denim/.test(d)) si(/mezclilla|denim|jeans?/.test(txt) ? true : (vacio(f.mezclilla) ? undefined : !!f.mezclilla), 10, 'mezclilla');
  if (f.tipo === 'pantalon' || f.tipo === 'enterizo'){
    if (/pantalones? largos?/.test(d)) si(vacio(f.largo) ? undefined : f.largo === 'largo', 5, 'largo');
    if (/\bcortos\b|shorts?|bermudas?/.test(d)) si(vacio(f.largo) ? undefined : f.largo === 'corto', 5, 'largo');
    if (/con peto|overol/.test(d)) si(vacio(f.peto) ? undefined : !!f.peto, 5, 'peto');
  }
  if (/manga larga/.test(d)) si(vacio(f.manga) ? undefined : f.manga === 'larga', 3, 'manga');
  if (/manga corta/.test(d)) si(vacio(f.manga) ? undefined : f.manga === 'corta', 3, 'manga');
  if (/sin mangas?/.test(d)) si(vacio(f.manga) ? undefined : f.manga === 'sin', 3, 'manga');
  if (/con cuello/.test(d)) si(vacio(f.conCuello) ? undefined : !!f.conCuello, 3, 'conCuello');
  if (/sin cuello/.test(d)) si(vacio(f.conCuello) ? undefined : !f.conCuello, 3, 'conCuello');
  if (/con capucha/.test(d)) si(vacio(f.capucha) ? undefined : !!f.capucha, 3, 'capucha');
  const comp = parseComp((f.comp || {}).exterior || '');
  if (/\bde algodon\b/.test(d) && comp && comp.pred){ if (comp.pred.grupo === 'algodon') sc += 1; else mal.push('algodon'); }
  const r = cifRango(d);
  if (r){ const v = parseFloat(f.valorCIF); if (isNaN(v)) faltan.push('valorCIF'); else if ((r.op === 'le' && v <= r.val) || (r.op === 'gt' && v > r.val)) sc += 2; else mal.push('cif'); }
  return {sc, choca: mal.length > 0, faltan: faltan.filter(x=>NAC_PREG.some(q=>q.id === x))};
}
function elegirInciso(f, opciones){
  const vivos = [];
  opciones.forEach(o=>{ const d = normDesc(o.desc || ''); const r = o.cond ? evaluarCond(o.cond, f) : evaluarOpcion(d, f); if (!r.choca && !(o.prio && r.faltan.length)) vivos.push({o, sc:r.sc + (o.prio || 0) * 10, demas:o.cond ? !Object.keys(o.cond).length : RE_DEMAS.test(d), faltan:r.faltan}); });
  if (vivos.length === 1) return {estado:'auto', o:vivos[0].o};
  if (!vivos.length) return {estado:'elegir', opciones, pedir:[]};
  const max = Math.max(...vivos.map(v=>v.sc)), top = vivos.filter(v=>v.sc === max);
  if (max >= 10 && top.length === 1) return {estado:'auto', o:top[0].o};
  const pedir = [...new Set(vivos.flatMap(v=>v.faltan))];
  if (pedir.length) return {estado:'elegir', opciones:top.map(v=>v.o).concat(vivos.filter(v=>!top.includes(v)).map(v=>v.o)), pedir};
  if (max > 0 && top.length === 1) return {estado:'auto', o:top[0].o};
  if (max === 0){ const dem = vivos.filter(v=>v.demas); if (dem.length === 1) return {estado:'auto', o:dem[0].o}; }
  return {estado:'elegir', opciones:top.map(v=>v.o).concat(vivos.filter(v=>!top.includes(v)).map(v=>v.o)), pedir:[]};
}
/* Condiciones de los incisos aprendidos: el sistema aprende el código nacional de lo que se confirma */
const COND_CAMPOS = [['genero',tr('Gender')],['edadNac',tr('Age')],['valorCIF',tr('CIF value')],['usoPrevisto',tr('Use')],['estiloCalz',tr('Footwear style')],['puntera',tr('Toe cap')],['altura',tr('Height')],['tejido',tr('Fabric')],['largo',tr('Length')],['manga',tr('Sleeve')],['mezclilla',tr('Denim')],['suelaEspumosa',tr('Foam sole')],['rodeaDedo',tr('Straps around the big toe')],['conCuello',tr('Collar')],['capucha',tr('Hood')],['peto',tr('Bib')],['sueter',tr('Sweater')],['formaTocado',tr('Headwear shape')],['claseBolso',tr('Bag class')]];
function valorCond(f, k){ return k === 'edadNac' ? edadDe(f) : f[k]; }
function textoValor(k, v){
  if (k === 'genero') return ({M:'men', F:'women', U:'unisex'})[v] || v;
  if (k === 'edadNac') return ({adulto:'adult', nino:'child', bebe:'baby'})[v] || v;
  if (Array.isArray(v)) return v.map(x=>textoValor(k, x)).join(' or ');
  if (typeof v === 'boolean') return (v ? '' : 'no ') + (COND_CAMPOS.find(c=>c[0] === k) || [k, k])[1].toLowerCase();
  const q = NAC_PREG.find(x=>x.id === k); if (q && q.ops) return ((q.ops.find(o=>o[0] === v) || [])[1] || v).toLowerCase();
  if (ATTR_BY[k]) return String(opcionLbl(k, v)).toLowerCase();
  return String(v);
}
function condTexto(c){
  if (!c || !Object.keys(c).length) return tr('the whole subheading');
  return Object.entries(c).map(([k, v])=>k === 'cifMax' ? 'CIF ≤ ' + v : k === 'cifMin' ? 'CIF > ' + v : textoValor(k, v)).join(', ');
}
function evaluarCond(cond, f){
  let sc = 0; const mal = [], faltan = [];
  Object.entries(cond || {}).forEach(([k, v])=>{
    if (k === 'cifMax' || k === 'cifMin'){ const x = parseFloat(f.valorCIF); if (isNaN(x)) faltan.push('valorCIF'); else if ((k === 'cifMax' && x <= v) || (k === 'cifMin' && x > v)) sc += 4; else mal.push(k); return; }
    const a = valorCond(f, k);
    if (vacio(a)){ if (NAC_PREG.some(q=>q.id === k)) faltan.push(k); return; }
    if (Array.isArray(v) ? v.map(String).includes(String(a)) : (typeof v === 'boolean' ? !!a === v : String(a) === String(v))) sc += 4; else mal.push(k);
  });
  return {sc, choca:mal.length > 0, faltan};
}
/* Condiciones que se pueden guardar al enseñar un código (lo que distingue a este producto) */
function condDeArticulo(f){
  return COND_CAMPOS.filter(([k])=>k !== 'valorCIF' && !vacio(valorCond(f, k)) && !(typeof valorCond(f, k) === 'boolean' && k !== 'mezclilla' && !valorCond(f, k))).map(([k, l])=>({k, l, v:valorCond(f, k)}));
}
/* Código de un país a partir de la partida base. ctx = {incisos, destinos} */
function partidaPais(f, iso, codBase, ctx){
  ctx = ctx || {};
  const ds = ctx.destinos, incisos = ctx.incisos || [];
  const cb = digits(codBase), sub = cb.slice(0,6), n = digitosPais(iso, ds);
  if (sub.length < 6) return {estado:'sin_codigo', codigo:''};
  let lista = incisosDe(iso, sub, incisos, ds);
  const dd = (ds || DESTINOS_BASE).find(x=>x.iso === iso);
  const esMcca = dd && dd.mcca !== undefined && dd.mcca !== null ? !!dd.mcca : MCCA5.includes(iso);
  const unaSac = () => esMcca && cb.length > 6 && cb.length >= Math.min(n, 10);
  const man = f.partidas && f.partidas[iso];
  if (man && man.manual && digits(man.codigo).startsWith(sub)){ const mc = digits(man.codigo).slice(0, n); const x = lista.find(y=>y.codigo === mc); return {codigo:mc, dai:x ? x.dai : (man.dai || ''), estado:'ok', desc:x ? x.desc : '', fuente:x ? x.fuente : 'manual'}; }
  if (n <= 6) return {codigo:sub, dai:lista.length === 1 ? lista[0].dai : '', estado:'ok', desc:descDe(sub), fuente:lista.length ? lista[0].fuente : ''};
  if (cb.length > 6){ const cbn = cb.slice(0, n); const m = lista.filter(x=>x.codigo.startsWith(cbn)); if (m.length === 1) return {codigo:m[0].codigo, dai:m[0].dai, estado:'ok', desc:m[0].desc, fuente:m[0].fuente}; if (m.length > 1) lista = m; }
  if (!lista.length){
    if (unaSac()) return {codigo:cb.slice(0, n), dai:'', estado:'sac'};
    const aprendidos = incisos.some(x=>x.pais === iso);
    return {codigo:sub, dai:'', estado: aprendidos ? 'nuevo' : 'sinarancel'};
  }
  if (lista.length === 1 && !(lista[0].cond && evaluarCond(lista[0].cond, f).choca)){ const r1 = lista[0].cond ? evaluarCond(lista[0].cond, f) : null; if (r1 && r1.faltan.length) return {estado:'elegir', codigo:'', opciones:lista, pedir:r1.faltan}; return {codigo:lista[0].codigo, dai:lista[0].dai, estado:'ok', desc:lista[0].desc, fuente:lista[0].fuente}; }
  if (lista.length === 1) return {codigo:unaSac() ? cb.slice(0, n) : sub, dai:'', estado:'nuevo'};
  const e = elegirInciso(f, lista);
  if (e.estado === 'auto') return {codigo:e.o.codigo, dai:e.o.dai, estado:'auto', desc:e.o.desc, fuente:e.o.fuente};
  return {estado:'elegir', codigo:'', opciones:e.opciones, pedir:e.pedir || []};
}
function partidasDe(f, codBase, ctx){
  const o = {}, ds = (ctx && ctx.destinos) || DESTINOS_BASE;
  ds.forEach(d=>{ const x = partidaPais(f, d.iso, codBase, ctx); o[d.iso] = {codigo:x.codigo || '', dai:x.dai == null ? '' : x.dai, estado:x.estado, digitos:digitosPais(d.iso, ds), fuente:x.fuente || '', desc:x.desc || '', opciones:x.opciones || null, pedir:x.pedir || []}; if (f.partidas && f.partidas[d.iso] && f.partidas[d.iso].manual) o[d.iso].manual = true; });
  return o;
}
/* Estado de un código de país: [clase, texto] */
const EST_PAIS = {ok:['ok',tr('National')], auto:['ok',tr('National')], sac:['sa','SAC'], sa:['sa',tr('Not in its tariff')], sinarancel:['sa',tr('No tariff loaded')], nuevo:['pend',tr('Not learned yet')], elegir:['elegir',tr('Needs data')], sin_codigo:['sa',tr('No code')]};
const FUENTE_PAIS = {arancel:tr('from the tariff'), manual:tr('by hand'), aprendido:'learned', base:'base', oficial:tr('official tariff (SIECA)')};
/* Completo cuando todos los países destino tienen su código a todos los dígitos */
function paisesCompletos(partidas, ds){
  return (ds || DESTINOS_BASE).every(d=>{ const x = (partidas || {})[d.iso]; return x && ['ok','auto'].includes(x.estado) && digits(x.codigo).length >= digitosPais(d.iso, ds); });
}

/* ---------- Ayudas del formulario ---------- */
/* Qué atributo se pregunta y cuál ya quedó definido por los datos (no se vuelve a preguntar) */
function estadoAttr(a, s){
  if (!a.aplica(s)) return 'oculto';
  if (a.tipo === 'check') return a.offCheck && a.offCheck(s) ? 'oculto' : 'preguntar';
  const fx = a.fijo ? a.fijo(s) : null;
  if (fx != null) return 'definido';
  if (a.deComp || a.soloNac || a.id === 'genero' || a.id === 'edad') return 'oculto';
  const ops = opcionesValidas(a, s);
  if (!ops.length) return 'oculto';
  if (ops.length === 1 && !a.info) return 'definido';
  return 'preguntar';
}
function motivoDefinido(a, s){
  if (a.deComp && a.fijo && a.fijo(s) != null) return 'composition';
  if (a.fijo && a.fijo(s) != null) return tr('product type');
  return tr('your choices');
}
const COMP_HINT = {
  prenda:tr('The fiber that weighs most in the outer fabric governs.'),
  calzado:tr('Upper: by external surface, excluding reinforcements and trims. Sole: by the surface that touches the ground.'),
  bolso:tr('The material of the outer surface governs.')
};
const MAT_NOMBRE = {algodon:tr('Cotton'), cotton:tr('Cotton'), poliester:tr('Polyester'), polyester:tr('Polyester'), rpet:tr('Recycled polyester'), nylon:tr('Nylon'), nilon:tr('Nylon'), poliamida:tr('Polyamide'), polyamide:tr('Polyamide'), elastano:tr('Elastane'), elastane:tr('Elastane'), spandex:tr('Elastane'), lycra:tr('Elastane'),
  viscosa:tr('Viscose'), viscose:tr('Viscose'), rayon:tr('Rayon'), modal:tr('Modal'), lyocell:tr('Lyocell'), tencel:tr('Lyocell'), lana:tr('Wool'), wool:tr('Wool'), merino:tr('Merino wool'), acrilico:tr('Acrylic'), acrylic:tr('Acrylic'), lino:tr('Linen'), linen:tr('Linen'), seda:tr('Silk'), silk:tr('Silk'),
  cuero:tr('Leather'), leather:tr('Leather'), piel:tr('Leather'), gamuza:tr('Suede'), suede:tr('Suede'), nubuck:tr('Nubuck'), nobuck:tr('Nubuck'), charol:tr('Patent leather'), patent:tr('Patent leather'), lona:tr('Canvas'), canvas:tr('Canvas'), malla:tr('Mesh'), mesh:tr('Mesh'), textil:tr('Textile'), textile:tr('Textile'), tela:tr('Textile'),
  sintetico:tr('Synthetic'), synthetic:tr('Synthetic'), pu:'PU', tpu:'TPU', tpr:'TPR', pvc:'PVC', eva:'EVA', caucho:tr('Rubber'), rubber:tr('Rubber'), goma:tr('Rubber'), hule:tr('Rubber'), latex:tr('Latex'), corcho:tr('Cork'), cork:tr('Cork'), neopreno:tr('Neoprene'), neoprene:tr('Neoprene'),
  plumon:tr('Down'), pluma:tr('Feather'), down:tr('Down'), feather:tr('Feather'), acero:tr('Stainless steel'), inoxidable:tr('Stainless steel'), stainless:tr('Stainless steel'), aluminio:tr('Aluminum'), aluminum:tr('Aluminum'), plastico:tr('Plastic'), plastic:tr('Plastic'), silicona:tr('Silicone'),
  metal:tr('Metal'), laton:tr('Brass'), zinc:tr('Zinc'), madera:tr('Wood'), wood:tr('Wood'), mdf:'MDF', papel:tr('Paper'), paper:tr('Paper'), carton:tr('Cardboard'), cartulina:tr('Card stock'), vidrio:tr('Glass'), paja:tr('Straw'), polipropileno:tr('Polypropylene'), satin:tr('Satin'), cordura:tr('Cordura'), fleece:tr('Polyester')};
const PARSE_LISTA = FIBRAS.concat(MAT_CALZ, [{g:'relleno', re:/\b(plumon|pluma|plumas|down|feathers?|goose|duck)\b/g}]);
function bonito(w){ const k = norm(w).trim(); return MAT_NOMBRE[k] || (w ? w.charAt(0).toUpperCase() + w.slice(1) : ''); }
/* Composición por filas: material | % */
function filasDesdeTexto(txt){
  const t = String(txt || '').trim(); if (!t) return [];
  const seg = segmentosComp(t)[0] || t;
  const pares = paresDe(prepMat(seg).s, PARSE_LISTA);
  if (!pares.length) return [{m:t, pct:''}];
  if (pares.length === 1 && pares[0].implicito) return [{m:bonito(pares[0].w), pct:'100'}];
  return pares.map(p=>({m:p.w ? bonito(p.w) : tr('Other'), pct:p.implicito ? '' : String(Math.round(p.pct * 10) / 10)}));
}
function textoDesdeFilas(rows){ return rows.filter(r=>String(r.m || '').trim()).map(r=>(r.pct !== '' && r.pct != null ? r.pct + '% ' : '') + String(r.m).trim()).join(', '); }
function totalFilas(rows){ return Math.round(rows.reduce((a,r)=>a + (parseFloat(String(r.pct).replace(',', '.')) || 0), 0) * 10) / 10; }
function totalTexto(txt){ return totalFilas(filasDesdeTexto(txt)); }
/* Materiales que se sugieren por parte: los que menciona el estilo y los típicos del tipo */
const SUG_DESC = [
  [/\b(suede|gamuza|ante)\b/, tr('Suede'), ['corte','exterior','material']], [/\b(nubuck|nobuck)\b/, tr('Nubuck'), ['corte']],
  [/\b(leather|cuero|piel)\b/, tr('Leather'), ['corte','exterior','material','forro']], [/\b(patent|charol)\b/, tr('Patent leather'), ['corte']],
  [/\b(canvas|lona)\b/, tr('Canvas'), ['corte','exterior']], [/\b(mesh|malla)\b/, tr('Mesh'), ['corte','forro','exterior']], [/\b(knit|flyknit|primeknit)\b/, tr('Textile'), ['corte']],
  [/\b(synthetic|sintetic[oa]|faux|vegan)\b/, tr('Synthetic'), ['corte','exterior','material']], [/\b(pvc)\b/, 'PVC', ['corte','exterior','material']],
  [/\b(rubber|goma|hule|vibram|caucho)\b/, tr('Rubber'), ['suela']], [/\b(eva|foam)\b/, 'EVA', ['suela','plantilla']], [/\b(cork|corcho)\b/, tr('Cork'), ['suela','plantilla']],
  [/\b(cotton|algodon|denim|jeans?|mezclilla|flannel|franela|chambray)\b/, tr('Cotton'), ['exterior','forro']], [/\b(polyester|poliester|fleece|polar|recycled)\b/, tr('Polyester'), ['exterior','forro']],
  [/\b(nylon|ripstop|cordura)\b/, tr('Nylon'), ['exterior','forro','material']], [/\b(wool|lana|merino)\b/, tr('Wool'), ['exterior']], [/\b(linen|lino)\b/, tr('Linen'), ['exterior']],
  [/\b(spandex|elastane|elastano|lycra|stretch)\b/, tr('Elastane'), ['exterior']], [/\b(rayon|viscose|viscosa|modal|tencel)\b/, tr('Viscose'), ['exterior']], [/\b(acrylic|acrilico)\b/, tr('Acrylic'), ['exterior']],
  [/\b(down|plumon|goose|duck|nuptse|puffer)\b/, tr('Down'), ['relleno']], [/\b(primaloft|thermoball|heatseeker|insulated)\b/, tr('Polyester'), ['relleno']],
  [/\b(stainless|acero|steel|inox)\b/, tr('Stainless steel'), ['material']], [/\b(aluminum|aluminio)\b/, tr('Aluminum'), ['material']], [/\b(plastic|plastico|tritan)\b/, tr('Plastic'), ['material']],
  [/\b(straw|paja)\b/, tr('Straw'), ['exterior']], [/\b(paper|papel|kraft)\b/, tr('Paper'), ['material']], [/\b(wood|madera)\b/, tr('Wood'), ['material']], [/\b(metal|metalic[oa])\b/, tr('Metal'), ['material']]
];
const UNIR = (...ls) => [...new Set(ls.flat())];
const TEXTIL_BASE = [tr('Cotton'),tr('Polyester'),tr('Nylon'),tr('Elastane'),tr('Viscose'),tr('Wool'),tr('Acrylic'),tr('Linen'),tr('Modal'),tr('Polyamide'),tr('Silk')];
function tipicosDe(p, s){
  const t = s.tipo, e = s.estiloCalz, g = grupoTipo(t);
  if (t === 'calzado'){
    if (p === 'corte') return UNIR(({tenis:[tr('Canvas'),tr('Suede'),tr('Leather'),tr('Mesh')], senderismo:[tr('Mesh'),tr('Suede'),tr('Nubuck'),tr('Leather')], bota:[tr('Leather'),tr('Nubuck'),tr('Suede')], botin:[tr('Leather'),tr('Suede'),tr('Synthetic')], zapato:[tr('Leather'),tr('Synthetic'),tr('Patent leather')], tacon:[tr('Synthetic'),tr('Leather'),tr('Patent leather')], mocasin:[tr('Leather'),tr('Suede'),tr('Nubuck')], sandalia:[tr('Synthetic'),tr('Leather'),tr('Textile')], slide:['EVA',tr('Rubber'),tr('Synthetic')], chancla_tetones:['EVA',tr('Rubber'),'PVC'], zueco:['EVA',tr('Rubber')], bota_lluvia:['PVC',tr('Rubber')], pantufla:[tr('Textile'),tr('Fleece'),tr('Synthetic')], seguridad:[tr('Leather'),tr('Nubuck'),tr('Synthetic')], tacos:[tr('Synthetic'),tr('Textile')]})[e] || [], [tr('Leather'),tr('Suede'),tr('Nubuck'),tr('Canvas'),tr('Mesh'),tr('Textile'),tr('Synthetic'),'PVC',tr('Patent leather'),tr('Neoprene')]);
    if (p === 'suela') return UNIR(({zapato:[tr('Rubber'),tr('Leather'),'TPR'], mocasin:[tr('Rubber'),tr('Leather')], tacon:['TPR','PU',tr('Leather')], sandalia:['EVA','TPR','PU',tr('Cork')], seguridad:[tr('Rubber'),'PU','TPU'], danza:[tr('Leather'),tr('Suede')]})[e] || [], [tr('Rubber'),'EVA','TPR','PU','TPU','PVC',tr('Leather'),tr('Cork')]);
    if (p === 'forro') return [tr('Textile'),tr('Polyester'),tr('Mesh'),tr('Leather'),tr('Synthetic'),tr('Cotton')];
    if (p === 'plantilla') return ['EVA','PU',tr('Latex'),tr('Textile'),tr('Leather'),tr('Cork')];
  }
  if (p === 'relleno') return [tr('Down'),tr('Feather'),tr('Polyester'),tr('Cotton'),tr('Wool')];
  if (p === 'forro') return g === 'bolso' ? [tr('Polyester'),tr('Nylon'),tr('Cotton'),tr('Mesh'),tr('Synthetic'),tr('Satin')] : [tr('Polyester'),tr('Nylon'),tr('Cotton'),tr('Viscose'),tr('Mesh'),tr('Satin')];
  if (p === 'exterior'){
    if (g === 'bolso') return [tr('Polyester'),tr('Nylon'),tr('Canvas'),tr('Leather'),tr('Synthetic'),'PVC',tr('Cotton'),tr('Cordura'),tr('Jute')];
    const m = {camiseta:[tr('Cotton'),tr('Polyester'),tr('Elastane')], camisa:[tr('Cotton'),tr('Polyester'),tr('Linen')], sudadera:[tr('Cotton'),tr('Polyester'),tr('Acrylic')], chaqueta:[tr('Nylon'),tr('Polyester'),tr('Cotton')], pantalon:[tr('Cotton'),tr('Polyester'),tr('Elastane'),tr('Nylon')],
      falda:[tr('Cotton'),tr('Viscose'),tr('Polyester')], vestido:[tr('Cotton'),tr('Viscose'),tr('Polyester'),tr('Elastane')], traje_bano:[tr('Polyester'),tr('Nylon'),tr('Elastane')], calcetines:[tr('Cotton'),tr('Polyester'),tr('Nylon'),tr('Elastane')], brasier:[tr('Polyester'),tr('Nylon'),tr('Elastane'),tr('Cotton')],
      guantes:[tr('Polyester'),tr('Acrylic'),tr('Nylon'),tr('Leather'),tr('Wool')], bufanda:[tr('Acrylic'),tr('Cotton'),tr('Polyester'),tr('Wool')], gorra:[tr('Cotton'),tr('Polyester'),tr('Acrylic'),tr('Wool'),tr('Nylon'),tr('Straw'),tr('Leather')],
      tienda:[tr('Polyester'),tr('Nylon'),tr('Cotton'),tr('Polypropylene'),tr('Canvas'),'PVC'], manta:[tr('Polyester'),tr('Cotton'),tr('Wool'),tr('Acrylic'),tr('Viscose'),tr('Nylon')], toalla:[tr('Cotton'),tr('Polyester'),tr('Nylon'),tr('Viscose'),tr('Linen')],
      colchoneta:[tr('Polyester'),tr('Nylon'),'PVC','TPU',tr('Cotton'),tr('Foam')], saco:[tr('Nylon'),tr('Polyester'),tr('Cotton'),tr('Wool'),tr('Silk')], polainas:[tr('Nylon'),tr('Polyester'),tr('Cordura'),tr('Neoprene'),tr('Elastane'),tr('Leather')]}[t];
    return UNIR(m || [], TEXTIL_BASE);
  }
  const mm = {cinturon:[tr('Leather'),tr('Synthetic'),tr('Canvas'),tr('Nylon'),tr('Polyester'),tr('Elastic'),tr('Metal')], botella:[tr('Stainless steel'),tr('Aluminum'),tr('Plastic'),tr('Tritan'),tr('Silicone'),tr('Glass')], llavero:[tr('Metal'),tr('Stainless steel'),tr('Brass'),tr('Leather'),tr('Nylon'),tr('Plastic'),tr('Silicone')],
    bisuteria:[tr('Stainless steel'),tr('Brass'),tr('Zinc'),tr('Leather'),tr('Textile'),tr('Plastic'),tr('Wood'),tr('Glass')], parche:[tr('Polyester'),tr('Cotton'),'PVC',tr('Paper'),tr('Vinyl'),tr('Nylon')], mascota:[tr('Nylon'),tr('Polyester'),tr('Leather'),tr('Cotton'),tr('Neoprene'),tr('Metal')],
    bolsa_compra:[tr('Paper'),tr('Card stock'),tr('Plastic'),tr('Polypropylene'),tr('Cotton'),tr('Polyester'),tr('Jute')], caja:[tr('Corrugated cardboard'),tr('Card stock'),tr('Paper'),tr('Plastic'),tr('Wood'),tr('Metal')], gancho:[tr('Plastic'),tr('Metal'),tr('Wire'),tr('Wood'),tr('Acrylic'),tr('Aluminum')],
    etiqueta:[tr('Paper'),tr('Cardboard'),tr('Polyester'),tr('Cotton'),'PVC',tr('Satin'),tr('Nylon')], exhibidor:[tr('Metal'),tr('Aluminum'),tr('Steel'),tr('Wood'),'MDF',tr('Acrylic plastic'),tr('Glass')], mueble_camping:[tr('Aluminum'),tr('Steel'),tr('Polyester'),tr('Nylon'),tr('Wood'),tr('Plastic')],
    linterna:[tr('Plastic'),tr('Aluminum'),'ABS',tr('Polycarbonate'),tr('Silicone'),tr('Metal')], bastones:[tr('Aluminum'),tr('Carbon'),tr('Steel'),tr('Cork'),tr('Rubber'),'EVA'], equipo_deporte:[tr('Foam'),tr('Nylon'),'PVC',tr('Polyester'),tr('Rubber'),'EVA'],
    patineta:[tr('Maple wood'),tr('Aluminum'),tr('Polyurethane'),tr('Steel'),tr('Plastic'),tr('Bamboo')], lentes_sol:[tr('Plastic'),tr('Polycarbonate'),tr('Metal'),tr('Acetate'),tr('Glass'),tr('Nylon')], sombrilla:[tr('Polyester'),tr('Nylon'),tr('Metal'),tr('Aluminum'),tr('Fiberglass'),tr('Plastic')],
    reloj:[tr('Plastic'),tr('Stainless steel'),tr('Silicone'),tr('Aluminum'),tr('Leather'),tr('Nylon')], plantilla:['EVA','PU',tr('Latex'),tr('Textile'),tr('Leather'),tr('Cork')], cordones:[tr('Polyester'),tr('Cotton'),tr('Nylon'),tr('Leather'),tr('Plastic'),tr('Elastic')],
    cuidado_calzado:[tr('Wax'),tr('Silicone'),tr('Plastic'),tr('Wood'),tr('Natural bristle'),tr('Nylon')],
    avios:[tr('Brass'),tr('Zinc'),tr('Steel'),tr('Aluminum'),tr('Plastic'),tr('Nylon'),tr('Polyester'),tr('Wood')], accesorio_pelo:[tr('Plastic'),tr('Acetate'),tr('Metal'),tr('Polyester'),tr('Satin'),tr('Cotton'),tr('Elastic')],
    correa_reloj:[tr('Silicone'),tr('Stainless steel'),tr('Leather'),tr('Nylon'),tr('Polyurethane'),tr('Titanium')], peleteria:[tr('Polyester'),tr('Acrylic'),tr('Modacrylic'),tr('Natural fur'),tr('Cotton'),tr('Nylon')], hamaca:[tr('Nylon'),tr('Polyester'),tr('Cotton'),tr('Ripstop'),tr('Canvas'),tr('Polypropylene')], magnesio:[tr('Magnesium carbonate'),tr('Alcohol'),tr('Rosin'),tr('Silica'),tr('Water'),tr('Resin')]}[t];
  return mm || [tr('Metal'),tr('Plastic'),tr('Leather'),tr('Textile'),tr('Wood'),tr('Paper')];
}
function nombreMat(w){ for (const [re, lbl] of SUG_DESC) if (re.test(w)) return lbl; return bonito(w); }
/* Sugerencias de materiales para una parte: los del estilo, los que más se usan en este tipo y los típicos */
function sugerenciasComp(p, s, recs){
  const usados = new Set(((s.comp || {})[p] ? filasDesdeTexto(s.comp[p]) : []).map(r=>norm(r.m).trim()));
  const texto = norm(textoDet(s) + ' ' + (s.uso || '') + ' ' + (s.marca || ''));
  const rel = [];
  SUG_DESC.forEach(([re, lbl, partes])=>{ if (partes.includes(p) && re.test(texto) && !rel.includes(lbl)) rel.push(lbl); });
  const cuenta = {};
  (recs || []).forEach(r=>{
    if (r.tipo !== s.tipo || !(r.comp && r.comp[p])) return;
    if (s.tipo === 'calzado' && s.estiloCalz && r.estiloCalz && r.estiloCalz !== s.estiloCalz) return;
    const peso = s.marca && norm(r.marca) === norm(s.marca) ? 2 : 1;
    filasDesdeTexto(r.comp[p]).forEach(x=>{ cuenta[x.m] = (cuenta[x.m] || 0) + peso; });
  });
  const frec = Object.entries(cuenta).sort((a,b)=>b[1] - a[1]).map(x=>x[0]);
  const vistos = new Set(), out = [];
  const meter = (m, fuente) => { const k = norm(m).trim(); if (!k || vistos.has(k) || usados.has(k)) return; vistos.add(k); out.push({m, fuente}); };
  rel.forEach(m=>meter(m, 'rel'));
  frec.slice(0, 5).forEach(m=>meter(m, 'base'));
  tipicosDe(p, s).forEach(m=>meter(m, 'tipico'));
  return {mats:out.slice(0, 10), todos:UNIR(rel, frec, tipicosDe(p, s))};
}
function partesPrincipales(t){ const g = grupoTipo(t); if (g === 'calzado') return ['corte','suela']; const ps = partesDe(t); return ps.includes('exterior') ? ['exterior'] : ps.includes('material') ? ['material'] : []; }
/* Datos obligatorios de la ficha técnica */
const OBLIG_CAMPOS = [['tipo',tr('Product type')],['genero',tr('Gender')],['edadNac',tr('Who it is for')],['uso',tr('What it is for')],['tallas',tr('Size range')],['composicion',tr('Main composition')],['origen',tr('Country of origin')],['fotos',tr('At least one photo')]];
const OBLIG_DEF = ['tipo','genero','edadNac','composicion','origen'];
function faltanObligatorios(f, obligatorios){
  const out = [];
  (obligatorios || OBLIG_DEF).forEach(k=>{
    const lbl = (OBLIG_CAMPOS.find(x=>x[0] === k) || [k, k])[1];
    if (k === 'composicion'){
      const pp = partesPrincipales(f.tipo);
      pp.forEach(p=>{ const v = String((f.comp || {})[p] || '').trim();
        if (!v) out.push({campo:'comp_' + p, label:tr('Composition: {0}', [PARTE_LBL[p].toLowerCase()])});
        else { const t = totalTexto(v); if (Math.abs(t - 100) > 0.05) out.push({campo:'comp_' + p, label:tr('{0} adds up to {1}%', [PARTE_LBL[p], t])}); } });
      const ma = MAT_ATTR[f.tipo]; if (!pp.length && ma && !f[ma]) out.push({campo:ma, label:ATTR_BY[ma].label});
      return;
    }
    if (k === 'fotos'){ if (!(f.fotos || []).length) out.push({campo:'fotos', label:lbl}); return; }
    if (k === 'edadNac'){ if (!edadDe(f)) out.push({campo:k, label:lbl}); return; }
    if (k === 'genero'){ if (!f.genero && ['prenda','calzado','gorra'].includes(grupoTipo(f.tipo))) out.push({campo:k, label:lbl}); return; }
    if (!String(f[k] || '').trim()) out.push({campo:k, label:lbl});
  });
  return out;
}
/* Ficha completa: obligatorios llenos y la regla llega a 6 dígitos */
function estadoFicha(f, obligatorios){
  const falt = faltanObligatorios(f, obligatorios).map(x=>x.label);
  const regla = f.tipo ? clasificarReglas(f) : null;
  if (f.tipo && (!regla || digits(regla.codigo).length < 6)) falt.push(regla && regla.faltantes[0] ? regla.faltantes[0] : tr('Data for the code'));
  return {completa: !falt.length, faltan: falt};
}
/* Texto de la ficha para la consulta al especialista */
function fichaTexto(f){
  const L = [];
  L.push(tr('Type: {0}', [TIPO_LBL[f.tipo] || tr('not given')]));
  [['marca',tr('Brand')],['estilo',tr('Style (product name)')],['desc',tr('Customs description')],['uso',tr('What it is for')],['color',tr('Color')],['origen',tr('Country of origin')],['tallas',tr('Size range')]].forEach(([k, l])=>{ if (f[k]) L.push(l + ': ' + f[k]); });
  partesDe(f.tipo, f).forEach(p=>{ if (f.comp && f.comp[p]) L.push(PARTE_LBL[p] + ': ' + f.comp[p]); });
  atributosLegibles(f).forEach(([k,v])=>L.push(k + ': ' + v));
  return L.join('\n');
}
/* Campos y valores que el especialista puede corregir */
function camposCorregibles(f){
  prepararEstado(f);
  const L = [tr('- tipo: {0}', [Object.keys(TIPO_LBL).join(', ')])];
  ATTRS.filter(a=>a.aplica(f)).forEach(a=>L.push('- ' + a.id + ' (' + a.label + '): ' + (a.tipo === 'check' ? tr('true or false') : a.ops.map(o=>o.v).join(', '))));
  partesDe(f.tipo, f).forEach(p=>L.push(tr('- comp.{0} ({1}): text with percentages, for example "60% suede, 40% canvas"', [p, PARTE_LBL[p]])));
  L.push(tr('- uso: short phrase of what it is for'));
  return L.join('\n');
}
function nombreCampo(c){ if (c.campo === 'tipo') return tr('Type'); if (c.campo === 'uso') return tr('What it is for'); if (c.campo.startsWith('comp.')) return PARTE_LBL[c.campo.slice(5)] || c.campo; return (ATTR_BY[c.campo] || {}).label || c.campo; }
function valorLegible(c){
  if (c.campo === 'tipo') return TIPO_LBL[c.valor] || c.valor;
  if (ATTR_BY[c.campo]) return opcionLbl(c.campo, ATTR_BY[c.campo].tipo === 'check' ? (c.valor === true || c.valor === 'true') : c.valor);
  return String(c.valor);
}
/* Clave estable de una alerta (para marcarla como revisada) */
const FUENTES = {regla:tr('Harmonized System rules'), historial:tr('Your history: product already classified'), criterio:tr('Your learned criteria')};
ESTADOS.observado = tr('Observed');
ESTADO_COLOR.observado = '#B42318';

/* Descripciones SAC cargadas en la base (se pueden editar y agregar) */
function setSac(lista){ (lista || []).forEach(x=>{ const c = digits(x.codigo); if (c.length >= 4 && x.descripcion) DESC[c] = x.descripcion; }); }
/* Descripción comercial en inglés, armada con la ficha técnica */
/* Descripción comercial: simple, como va en la factura y el packing list:
   el tipo de producto en español y la marca (p. ej. "CALZADO VANS"). */
function tipoComercial(f){
  const t = f.tipo; if (!t) return '';
  if (grupoTipo(t) === 'calzado' || t === 'calzado') return 'CALZADO';
  if (t === 'chaqueta') return ['chaleco','chaleco_relleno','reflectivo'].includes(f.hechura) ? 'CHALECO' : f.hechura === 'blazer' ? 'SACO' : 'CHAQUETA';
  if (t === 'pantalon') return f.largo === 'corto' ? 'SHORT' : 'PANTALÓN';
  if (t === 'camiseta') return f.polo ? 'POLO' : 'CAMISETA';
  if (t === 'sudadera') return f.sueter ? 'SUÉTER' : 'SUDADERA';
  if (t === 'otro_sac') return nombreOtro(f).split(/[ ,]/).slice(0, 3).join(' ');
  return String(TIPO_CORTO_ES[t] || TIPO_CORTO[t] || t).split(' o ')[0].toUpperCase();
}
function descripcionComercial(f){
  const tipo = tipoComercial(f); if (!tipo) return '';
  return (tipo + ' ' + String(f.marca || '').trim()).trim().toUpperCase();
}

export {
  norm, digits, fmtCode, fmtPais, descDe, setSac, descripcionComercial, tipoComercial, TIPO_CORTO_ES, CAPITULOS, DESC, DESTINOS_BASE, MCCA5, notaOrigenDestino,
  TIPOS, TIPO_LBL, TIPO_CORTO, buscarTipos, grupoTipo, partesDe, partesPrincipales, PARTE_LBL, PARTE_PH,
  FIB_LBL, MAT_LBL, MAT_EQUIV, MAT_AMBIGUAS, setSinonimos, claseTexto, CLASE_LBL, prepMat, parseComp, parseMat, claseMat, resumenMat, segmentosComp,
  ATTRS, ATTR_BY, ATTR_IDS, opcionLbl, opcionesValidas, prepararEstado, normalizar, aplicarImplica, atributosLegibles, estadoAttr, motivoDefinido,
  detectar, detectarFicha, detectarCon, parseTallas, edadDe, descripcionProfesional, clasificarReglas, sugerir, perfilDe, perfilLegible,
  validar, verificarCodigo, alertaKey, alertasVivas, evaluar, ESTADOS, ESTADO_COLOR, EDAD_LBL, FUENTES,
  digitosPais, incisosDe, incisosBase, partidaPais, partidasDe, paisesCompletos, EST_PAIS, FUENTE_PAIS, NAC_PREG, NAC_IDS, detectarNac,
  COND_CAMPOS, condTexto, condDeArticulo, valorCond, textoValor, vacio,
  COMP_HINT, filasDesdeTexto, textoDesdeFilas, totalFilas, totalTexto, sugerenciasComp, nombreMat, bonito,
  OBLIG_CAMPOS, OBLIG_DEF, faltanObligatorios, estadoFicha, fichaTexto, camposCorregibles, nombreCampo, valorLegible,
}
