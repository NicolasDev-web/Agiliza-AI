import numpy as np
import pandas as pd

from transporte import calendario as cal

HOL = np.array(["2026-11-02"], dtype="datetime64[D]")


def test_exemplo_da_regra_pedido_na_quarta_prazo_4():
    # parametros.md: quarta -> quinta(1), sexta(2), segunda(3), terça(4)
    r = cal.somar_dias_uteis(np.datetime64("2026-08-05"), 4, np.array([], dtype="datetime64[D]"))
    assert str(r) == "2026-08-11"


def test_pedido_no_fim_de_semana_conta_a_partir_da_segunda():
    # sábado 08/08: o dia 1 é segunda 10/08
    assert str(cal.somar_dias_uteis(np.datetime64("2026-08-08"), 1, np.array([], dtype="datetime64[D]"))) == "2026-08-10"


def test_feriado_nacional_nao_conta():
    # sexta 30/10 + 1 dia útil: segunda 02/11 é Finados, então vai para terça 03/11
    assert str(cal.somar_dias_uteis(np.datetime64("2026-10-30"), 1, HOL)) == "2026-11-03"


def test_dias_uteis_entre_e_inverso_de_somar():
    a = np.datetime64("2026-09-01")
    for n in range(1, 12):
        fim = cal.somar_dias_uteis(a, n)
        assert int(cal.dias_uteis_entre(a, fim)) == n


def test_dias_uteis_entre_nao_fica_negativo():
    assert int(cal.dias_uteis_entre(np.datetime64("2026-09-10"), np.datetime64("2026-09-08"))) == 0
