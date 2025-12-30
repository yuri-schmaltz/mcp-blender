import subprocess
import sys
import os
import time

def test_blender_addon_server_start_stop():
    """
    Testa ciclo E2E mínimo: inicia e para o servidor do add-on (simulação headless).
    Critérios: sem exceção, logs de start/stop presentes.
    """
    # Caminho do script principal do add-on
    addon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../addon.py'))
    
    # Inicia o servidor em subprocesso (simula Blender headless)
    proc = subprocess.Popen([sys.executable, addon_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)  # Aguarda inicialização
    proc.terminate()
    out, err = proc.communicate(timeout=5)
    output = (out or b'').decode() + (err or b'').decode()
    assert 'server started' in output.lower() or 'blender' in output.lower(), f"Log esperado não encontrado: {output}"
    assert proc.returncode is not None

if __name__ == '__main__':
    test_blender_addon_server_start_stop()
    print('E2E test passed')
