from __future__ import annotations

from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.exporting.story_export import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    build_export_bundle,
    render_export_artifact,
)


def test_build_export_bundle_includes_rich_artifacts() -> None:
    world = WorldState(title="赤潮纪", premise="一场帝国边境上的异变")
    character = Character(
        name="沈砚",
        description="守城将军",
        personality="克制",
        goals=["守住赤潮关", "查明异变"],
    )
    world.add_character(character)
    world.world_rules = ["血月升起时，潮水会逆流。"]
    world.factions = [{"name": "北境军", "description": "守城军团"}]
    world.locations = [{"name": "赤潮关", "description": "帝国北方要塞"}]

    bundle = build_export_bundle(
        "sim-export",
        "main",
        world,
        [
            {
                "tick": 1,
                "title": "边关失火",
                "node_type": "setup",
                "description": "城头出现诡异红光",
                "rendered_text": "第一段正文",
                "editor_html": "<p><strong>第一段正文</strong></p>",
                "scene_script_summary": "城头红光被 GM 结算为可渲染事实。",
                "narrator_input_source": "scene_script",
                "branch_id": "main",
            }
        ],
    )

    assert bundle["sim_id"] == "sim-export"
    assert bundle["branch_id"] == "main"
    assert bundle["summary"]["node_count"] == 1
    assert bundle["summary"]["character_count"] == 1
    assert bundle["markdown"].startswith("# 赤潮纪")
    assert "## 边关失火" in bundle["markdown"]
    assert "<strong>第一段正文</strong>" in bundle["html"]
    assert bundle["story_sections"][0]["prose"] == "第一段正文"
    assert bundle["world_settings"]["characters"][0]["description"] == "守城将军"
    assert bundle["timeline"][0]["branch_id"] == "main"
    manifest_kinds = {item["kind"] for item in bundle["manifest"]["files"]}
    assert manifest_kinds == {
        "novel_txt",
        "novel_markdown",
        "novel_html",
        "novel_docx",
        "novel_pdf",
        "world_settings_json",
        "timeline_json",
        "manifest_json",
    }

    docx_name, docx_type, docx_bytes = render_export_artifact(bundle, "novel_docx")
    pdf_name, pdf_type, pdf_bytes = render_export_artifact(bundle, "novel_pdf")

    assert docx_name.endswith(".docx")
    assert docx_type == DOCX_MIME_TYPE
    assert docx_bytes[:2] == b"PK"
    assert pdf_name.endswith(".pdf")
    assert pdf_type == PDF_MIME_TYPE
    assert pdf_bytes.startswith(b"%PDF")
