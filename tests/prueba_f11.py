"""F11: propuestas deterministas. Cada propuesta es el mismo valor que usa el motor o la ficha del informe (regla 13):
si una de las dos cambia y la otra no, estas pruebas fallan. Sin red (EDGAR y la bolsa desde tests/fixtures)."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from tesis.entradas import proponer
from tesis.motor import supuestos
from tests.prueba_f6 import _Datos

FECHA = date(2026, 9, 23)
FECHA_BOLSA = date(2026, 9, 22)      # la última sesión con la respuesta de la bolsa congelada en tests/fixtures


class MismaFuenteQueElMotor(unittest.TestCase):
    """Sin entradas, el motor toma cada parámetro de la misma función que lo propone el asistente."""

    def test_valores_de_partida(self):
        p = supuestos.leer({}, FECHA)
        del_motor = {"val.mitad_de_anio": p.mitad_de_anio, "val.sbc": p.sbc_politica, "val.arrendamientos": p.arrendamientos,
                     "wacc.beta_metodo": p.beta_metodo, "wacc.prima": p.prima * 100, "wacc.kd_metodo": p.kd_metodo,
                     "wacc.tipo_marginal": round(p.tipo_marginal * 100, 9), "tv.metodo": p.tv_metodo}
        ctx = proponer.Contexto("QCOM", FECHA, {})
        for campo, valor in del_motor.items():
            self.assertEqual(proponer._REGISTRO[campo](ctx).valor, valor, campo)

    def test_periodo_y_horizonte(self):
        for paquete in ("general", "semiconductores", "software"):
            datos = {"meta": {"sector": paquete}}
            ctx = proponer.Contexto("QCOM", FECHA, datos)
            self.assertEqual(proponer._REGISTRO["val.periodo_explicito"](ctx).valor, supuestos.leer(datos, FECHA).periodo, paquete)
        self.assertEqual(proponer._REGISTRO["val.horizonte_meses"](proponer.Contexto("QCOM", FECHA, {})).valor,
                         supuestos.leer({}, FECHA).horizonte_meses)
        # hoy todas las horquillas acaban en 10: un 10 escrito en el motor coincidiría por casualidad. Con una que acaba en 8,
        # los dos tienen que decir 8
        from tesis.motor import datos as motor_datos
        cfg = dict(motor_datos.sectores())
        cfg["paquetes"] = dict(cfg["paquetes"], prueba={"periodo": [5, 8]})
        with mock.patch.object(motor_datos, "sectores", return_value=cfg):
            datos = {"meta": {"sector": "prueba"}}
            self.assertEqual(proponer._REGISTRO["val.periodo_explicito"](proponer.Contexto("QCOM", FECHA, datos)).valor, 8)
            self.assertEqual(supuestos.leer(datos, FECHA).periodo, 8)

    def test_un_valor_de_partida_sin_configurar_es_un_error(self):
        """Falla si un valor que falta en config/propuestas.yaml se rellena con uno escondido en código."""
        with self.assertRaises(KeyError):
            proponer.por_defecto("val.no_existe")


class ConDatos(_Datos):
    def test_fecha_y_precio_de_valoracion(self):
        """Falla si la fecha de valoración no es la última sesión cerrada de Nasdaq o el precio de entrada no es su cierre."""
        from tesis.fuentes import precio
        props = proponer.proponer("QCOM", FECHA_BOLSA, {})
        fv = date.fromisoformat(props["meta.fecha_valoracion"].valor)
        self.assertLessEqual(fv, FECHA_BOLSA)
        sesiones = precio.sesiones_nasdaq("QCOM", precio.desde_5a(FECHA_BOLSA), FECHA_BOLSA, limite=2000)
        self.assertEqual(fv, max(d for d in sesiones if d <= FECHA_BOLSA))
        self.assertEqual(props["pos.precio_entrada"].valor, round(sesiones[fv].cierre, 2))
        self.assertEqual(props["pos.fecha_entrada"].valor, fv.isoformat())

    def test_plantilla_y_fundacion_son_las_de_la_ficha(self):
        """Falla si el asistente propone una plantilla o una fecha de fundación distinta de la que imprime la ficha."""
        from tesis.datos import ficha
        from tesis.fuentes import sec
        portada = sec.portada_10k(sec.emisor("QCOM"))
        f = ficha.Ficha(emisor=sec.emisor("QCOM"))
        ficha._propuestas_de_texto(f, portada)
        props = proponer.proponer("QCOM", FECHA, {})
        self.assertEqual(props["perfil.empleados"].valor, f.citas["empleados"].valor)
        self.assertEqual(props["perfil.fundacion"].valor, f.citas["fundacion"].valor)
        self.assertIn("«", props["perfil.empleados"].motivo)          # con la frase literal del 10-K

    def test_anio_base(self):
        """LTM con dos o más 10-Q tras el último 10-K a la fecha del informe; si no, el último ejercicio."""
        self.assertEqual(proponer.proponer("QCOM", FECHA, {})["val.anio_base"].valor, "ultimos_12_meses")
        self.assertEqual(proponer.proponer("QCOM", date(2025, 12, 1), {})["val.anio_base"].valor, "ultimo_ejercicio")

    def test_fechas_de_revision_publicadas_o_del_horizonte(self):
        props = proponer.proponer("QCOM", FECHA_BOLSA, {})
        fechas = props["pos.fechas_revision"].valor
        fv = date.fromisoformat(props["meta.fecha_valoracion"].valor)
        self.assertEqual(fechas[-1], date(fv.year + 1, fv.month, fv.day).isoformat())
        self.assertTrue(all(date.fromisoformat(x) > FECHA_BOLSA for x in fechas))

    def test_kpis_del_paquete_sin_verde_ni_rojo(self):
        """Falla si los KPI propuestos traen umbrales: el verde y el rojo son del analista."""
        k = proponer.proponer("QCOM", FECHA, {"meta": {"sector": "semiconductores"}})["pos.kpis"]
        self.assertIn("borrador", k.fuente)
        self.assertTrue(k.valor and all(set(x) == {"kpi", "fuente", "frecuencia"} for x in k.valor))

    def test_erp_solo_con_fuente_y_fecha_vigentes(self):
        """Falla si se propone una ERP sin fichero, sin fuente o más antigua que el umbral."""
        self.assertIsInstance(proponer.proponer("QCOM", FECHA, {})["wacc.erp"], proponer.SinPropuesta)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "erp.yaml").write_text("valor: 4.3\nfuente: Analista\nfecha: 2026-09-01\n", encoding="utf-8")
            with mock.patch("tesis.rutas.CONFIG", Path(tmp)):
                ctx = proponer.Contexto("QCOM", FECHA, {})
                self.assertEqual(proponer._REGISTRO["wacc.erp"](ctx).valor, 4.3)
                (Path(tmp) / "erp.yaml").write_text("valor: 4.3\nfuente: Analista\nfecha: 2026-01-01\n", encoding="utf-8")
                self.assertIsInstance(proponer._REGISTRO["wacc.erp"](ctx), proponer.SinPropuesta)
                (Path(tmp) / "erp.yaml").write_text("valor: 4.3\nfecha: 2026-09-01\n", encoding="utf-8")
                self.assertIsInstance(proponer._REGISTRO["wacc.erp"](ctx), proponer.SinPropuesta)


if __name__ == "__main__":
    unittest.main()
