import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from core.radio_streamer import RadioStreamer, get_best_stream_proxy, resolve_stream_info
from core.audio_engine import AudioEngine
from ui.fluent_main_window import FluentMainWindow

def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)

    print('--- Testing Proxy Detection ---')
    proxy = get_best_stream_proxy()
    print(f'Detected Proxy: {proxy}')
    assert proxy is not None, 'Expected proxy to be detected'

    print('--- Testing Clean Audio Devices ---')
    devs = AudioEngine.get_audio_devices()
    outputs = devs['outputs']
    inputs = devs['inputs']
    print(f'Outputs count: {len(outputs)}')
    for d in outputs:
        print(f"  Out: {d['name']} (HostAPI: {d['hostapi']})")
        assert 'wdm-ks' not in d['hostapi'].lower(), 'WDM-KS should be filtered!'
    print(f'Inputs count: {len(inputs)}')
    for d in inputs:
        print(f"  In:  {d['name']} (HostAPI: {d['hostapi']})")
        assert 'wdm-ks' not in d['hostapi'].lower(), 'WDM-KS should be filtered!'

    print('--- Testing Window Creation and Dynamic Taskbar Icons ---')
    win = FluentMainWindow()

    # Check UI buttons in radio tab
    radio_ui = win.radio_interface
    assert hasattr(radio_ui, 'btn_play_custom'), 'btn_play_custom missing'
    assert hasattr(radio_ui, 'btn_preview_custom'), 'btn_preview_custom missing'
    assert hasattr(radio_ui, 'btn_open_browser'), 'btn_open_browser missing'
    print(f'btn_play_custom text: {radio_ui.btn_play_custom.text()}')
    print(f'btn_preview_custom text: {radio_ui.btn_preview_custom.text()}')
    print(f'btn_open_browser text: {radio_ui.btn_open_browser.text()}')
    print(f'btn_stop text: {radio_ui.btn_stop.text()}')
    assert radio_ui.btn_stop.text() == 'Воспроизвести', 'Initial btn_stop should be Воспроизвести'

    # Check target mic combo
    combo_mic = radio_ui.combo_target_mic
    print(f'combo_target_mic count: {combo_mic.count()}')
    for i in range(combo_mic.count()):
        text = combo_mic.itemText(i)
        print(f'  item {i}: {text}')
        assert not text.startswith('['), f'Item {text} should not start with ['

    # Check active icon frames
    assert len(win.active_icon_frames) == 6, 'Should have 6 pre-rendered active frames'
    print('6 Active icon animation frames pre-rendered successfully')

    # Check audio activity detection
    print(f'Initial is_audio_active: {win.engine.is_audio_active}')
    assert not win.engine.is_audio_active, 'Engine should be idle initially'

    # Simulate sound play
    win.engine.play_sound('test_sfx', 'assets/sounds/coin.wav', volume=1.0)
    print(f'After playing sound is_audio_active: {win.engine.is_audio_active}')
    assert win.engine.is_audio_active, 'Engine should be active when sound is playing'

    # Trigger taskbar update
    win._update_taskbar_icon_state()
    assert win._is_taskbar_active, '_is_taskbar_active should be True'
    print('Taskbar icon successfully updated to active frame!')

    # Stop all sounds
    win.engine.stop_all()
    assert not win.engine.is_audio_active, 'Engine should be idle after stop_all'
    win._update_taskbar_icon_state()
    assert not win._is_taskbar_active, '_is_taskbar_active should be False'
    print('Taskbar icon successfully restored to idle state!')

    win._quit_app()
    print('>>> ALL CHECKS PASSED!')

if __name__ == '__main__':
    run_tests()
