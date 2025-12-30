# handlers/scene.py - Handler de cena com robustez e logging
import logging

def get_scene_info():
    """Obtém informações da cena atual do Blender."""
    logger = logging.getLogger("Handler.Scene")
    try:
        # Simulação de acesso à API do Blender
        # info = bpy.context.scene.name
        info = "CenaTeste"  # Placeholder
        logger.info(f"Scene info obtido: {info}")
        return {"status": "success", "scene": info}
    except Exception as e:
        logger.error(f"Erro ao obter info da cena: {e}")
        return {"status": "error", "message": str(e)}
