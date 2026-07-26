#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Golden-тесты для clean_model_and_version из rom_common.
Фиксируют текущее поведение именования, чтобы регрессии ловились автоматически.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rom_common import clean_model_and_version, get_usb_root, get_file_sha256


def test_aputure_standard():
    """Aputure: стандартное описание с версией — слова после версии остаются"""
    model, ver = clean_model_and_version("STORM 1200x V1.04.02 firmware", "Aputure")
    assert model == "STORM 1200x firmware", f"Expected STORM 1200x firmware, got {model}"
    assert ver == "V1.04.02", f"Expected V1.04.02, got {ver}"


def test_aputure_no_version():
    """Aputure: описание без версии — возвращается как есть"""
    model, ver = clean_model_and_version("STORM 1200x firmware", "Aputure")
    assert model == "STORM 1200x firmware", f"Expected STORM 1200x firmware, got {model}"
    assert ver == "", f"Expected empty version, got {ver}"


def test_aputure_amaran_filter():
    """Aputure: описание с amaran — фильтруется"""
    model, ver = clean_model_and_version("Amaran 60c V1.2.0", "Aputure")
    assert model == "", f"Expected empty model (Amaran under Aputure), got {model}"
    assert ver == "", f"Expected empty version, got {ver}"


def test_amaran():
    """Amaran: корректный бренд — бренд отрезается от модели"""
    model, ver = clean_model_and_version("AMARAN 60c V1.2.0", "Amaran")
    assert model == "60c", f"Expected 60c, got {model}"
    assert ver == "V1.2.0", f"Expected V1.2.0, got {ver}"


def test_godox_continuous():
    """Godox: continuous light firmware"""
    model, ver = clean_model_and_version("EVOKE 1200B V1.04.02.zip", "Godox")
    assert model == "EVOKE 1200B", f"Expected EVOKE 1200B, got {model}"
    assert ver == "V1.04.02", f"Expected V1.04.02, got {ver}"


def test_godox_no_version():
    """Godox: без версии"""
    model, ver = clean_model_and_version("EVOKE 1200B firmware", "Godox")
    assert model == "EVOKE 1200B", f"Expected EVOKE 1200B, got {model}"
    assert ver == "", f"Expected empty version, got {ver}"


def test_nanlite():
    """Nanlite: API описание — uppercase"""
    model, ver = clean_model_and_version("Forza 60C V2.01.22 firmware", "Nanlite")
    assert model == "FORZA 60C", f"Expected FORZA 60C, got {model}"
    assert ver == "V2.01.22", f"Expected V2.01.22, got {ver}"


def test_nanlux():
    """Nanlux: API описание — uppercase"""
    model, ver = clean_model_and_version("Evoke 2400B V3.0 firmware", "Nanlux")
    assert model == "EVOKE 2400B", f"Expected EVOKE 2400B, got {model}"
    assert ver == "V3.0", f"Expected V3.0, got {ver}"


def test_arri():
    """ARRI: бренд отрезается, uppercase"""
    model, ver = clean_model_and_version("ARRI SkyPanel S60 V1.2.3 firmware", "ARRI")
    assert model == "SKYPANEL S60", f"Expected SKYPANEL S60, got {model}"
    assert ver == "V1.2.3", f"Expected V1.2.3, got {ver}"


def test_astera():
    """Astera: описание с Titan — uppercase, бренд отрезается"""
    model, ver = clean_model_and_version("Astera Titan V3.0.1 firmware", "Astera")
    assert model == "TITAN", f"Expected TITAN, got {model}"
    assert ver == "V3.0.1", f"Expected V3.0.1, got {ver}"


def test_creamsource_vortex():
    """Creamsource: Vortex модель"""
    model, ver = clean_model_and_version("Vortex V1.04.02 firmware", "Creamsource")
    assert model == "Vortex", f"Expected Vortex, got {model}"
    assert ver == "V1.04.02", f"Expected V1.04.02, got {ver}"


def test_creamsource_sky():
    """Creamsource: Sky модель"""
    model, ver = clean_model_and_version("Sky firmware update V1.0", "Creamsource")
    assert model == "Sky", f"Expected Sky, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_litegear_litemat():
    """LiteGear: LiteMat модель"""
    model, ver = clean_model_and_version("LiteMat 2L V2.0.0 firmware", "LiteGear")
    assert model == "LiteMat", f"Expected LiteMat, got {model}"
    assert ver == "V2.0.0", f"Expected V2.0.0, got {ver}"


def test_litegear_liteblade():
    """LiteGear: LiteBlade модель"""
    model, ver = clean_model_and_version("LiteBlade 12 V1.0 firmware", "LiteGear")
    assert model == "LiteBlade", f"Expected LiteBlade, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_lightstar_qlion():
    """Lightstar: Q-Lion модель"""
    model, ver = clean_model_and_version("Q-Lion 600 Pro V1.2 firmware", "Lightstar")
    assert model == "Q-Lion", f"Expected Q-Lion, got {model}"
    assert ver == "V1.2", f"Expected V1.2, got {ver}"


def test_lightstar_celeb():
    """Lightstar: Celeb модель"""
    model, ver = clean_model_and_version("Celeb 200 V2.0 firmware", "Lightstar")
    assert model == "Celeb", f"Expected Celeb, got {model}"
    assert ver == "V2.0", f"Expected V2.0, got {ver}"


def test_litepanels():
    """Litepanels: Gemini модель — '1x1' не извлекается"""
    model, ver = clean_model_and_version("Gemini 1x1 V3.0.1 firmware", "Litepanels")
    assert model == "Gemini", f"Expected Gemini, got {model}"
    assert ver == "V3.0.1", f"Expected V3.0.1, got {ver}"


def test_quasar():
    """Quasar Science: модель — отдаётся только первое слово"""
    model, ver = clean_model_and_version("Q-Lion Cross 4x4 V1.0 firmware", "Quasar Science")
    assert model == "Q", f"Expected Q, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_kinoflo_select():
    """Kino Flo: Select модель"""
    model, ver = clean_model_and_version("Select 30 V1.0 firmware", "Kino Flo")
    assert model == "Select", f"Expected Select, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_kinoflo_freestyle():
    """Kino Flo: Freestyle модель"""
    model, ver = clean_model_and_version("Freestyle 20 V2.0 firmware", "Kino Flo")
    assert model == "Freestyle", f"Expected Freestyle, got {model}"
    assert ver == "V2.0", f"Expected V2.0, got {ver}"


def test_pipelighting_colorpipe():
    """Pipe Lighting: ColorPipe модель"""
    model, ver = clean_model_and_version("ColorPipe 20 V1.0 firmware", "Pipe Lighting")
    assert model == "ColorPipe", f"Expected ColorPipe, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_pheonlux_freestyle():
    """Pheon Lux: Freestyle модель"""
    model, ver = clean_model_and_version("Freestyle 100 V1.0 firmware", "Pheon Lux")
    assert model == "Freestyle", f"Expected Freestyle, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_gvm():
    """GVM: бренд отрезается от модели"""
    model, ver = clean_model_and_version("GVM 800D V2.0 firmware", "GVM")
    assert model == "800D", f"Expected 800D, got {model}"
    assert ver == "V2.0", f"Expected V2.0, got {ver}"


def test_knowled():
    """Knowled: стандартное описание"""
    model, ver = clean_model_and_version("Knowled 900C V1.5 firmware", "Knowled")
    # Note: Knowled may be handled by Godox scrapers
    assert ver == "V1.5", f"Expected V1.5, got {ver}"


def test_download_noise():
    """Шумовые описания (download, link и т.д.) — возврат пустых строк"""
    model, ver = clean_model_and_version("download", "Aputure")
    assert model == "", f"Expected empty, got {model}"
    assert ver == "", f"Expected empty, got {ver}"


def test_download_pdf_noise():
    """Шум 'download pdf'"""
    model, ver = clean_model_and_version("download pdf", "Nanlite")
    assert model == "", f"Expected empty, got {model}"
    assert ver == "", f"Expected empty, got {ver}"


def test_view_full_noise():
    """Шум 'view full change log'"""
    model, ver = clean_model_and_version("view full change log", "Godox")
    assert model == "", f"Expected empty, got {model}"
    assert ver == "", f"Expected empty, got {ver}"


def test_version_with_underscore():
    """Версия с подчёркиванием перед ней — модель до версии"""
    model, ver = clean_model_and_version("STORM_1200x_V1.04.02", "Aputure")
    assert model == "STORM", f"Expected STORM, got {model}"
    assert ver == "V1.04.02", f"Expected V1.04.02, got {ver}"


def test_major_minor_version():
    """Версия только major.minor (без patch) — uppercase"""
    model, ver = clean_model_and_version("Evoke 2400B V3.0", "Nanlux")
    assert model == "EVOKE 2400B", f"Expected EVOKE 2400B, got {model}"
    assert ver == "V3.0", f"Expected V3.0, got {ver}"


def test_multi_part_version():
    """Версия из 3 частей"""
    model, ver = clean_model_and_version("SkyPanel S60 V1.2.3", "ARRI")
    assert ver == "V1.2.3", f"Expected V1.2.3, got {ver}"


def test_version_without_v_prefix():
    """Версия без префикса V"""
    model, ver = clean_model_and_version("Forza 60C 2.01.22 firmware", "Nanlite")
    assert model == "FORZA 60C", f"Expected FORZA 60C, got {model}"
    assert ver in ("2.01.22", "V2.01.22"), f"Expected 2.01.22 or V2.01.22, got {ver}"


def test_unknown_brand():
    """Неизвестный бренд — uppercase"""
    model, ver = clean_model_and_version("Mystery Light 5000 V1.0", "Unknown")
    assert model == "MYSTERY LIGHT 5000", f"Expected MYSTERY LIGHT 5000, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_dmx_chart():
    """DMX chart описание — 'Chart' не вырезается"""
    model, ver = clean_model_and_version("STORM 1200x DMX Chart V1.0", "Aputure")
    assert model == "STORM 1200x DMX", f"Expected STORM 1200x DMX, got {model}"
    assert ver == "V1.0", f"Expected V1.0, got {ver}"


def test_empty_description():
    """Пустое описание"""
    model, ver = clean_model_and_version("", "Aputure")
    assert model == "", f"Expected empty, got {model}"
    assert ver == "", f"Expected empty, got {ver}"


def test_description_with_file_ext():
    """Описание с расширением файла на конце"""
    model, ver = clean_model_and_version("EVOKE_1200B_V1.04.02.zip", "Godox")
    assert model == "EVOKE 1200B", f"Expected EVOKE 1200B, got {model}"
    assert ver == "V1.04.02", f"Expected V1.04.02, got {ver}"


def test_arri_canto_description():
    """ARRI Canto: uppercase, 'firmware' в модели"""
    model, ver = clean_model_and_version("Orbiter V1.1.0 firmware update", "ARRI")
    assert model == "ORBITER FIRMWARE", f"Expected ORBITER FIRMWARE, got {model}"
    assert ver == "V1.1.0", f"Expected V1.1.0, got {ver}"


if __name__ == "__main__":
    # Collect all test_* functions and run them
    import types
    this_module = sys.modules[__name__]
    tests = [(name, fn) for name, fn in vars(this_module).items()
             if name.startswith("test_") and isinstance(fn, types.FunctionType)]
    tests.sort(key=lambda x: x[0])

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Passed: {passed}, Failed: {failed}, Total: {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
