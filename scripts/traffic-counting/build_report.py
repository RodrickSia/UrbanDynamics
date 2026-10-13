"""Make a standalone artifact review page; does not modify the team's frontend."""
import argparse
from html import escape
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--runs-dir", default="outputs/visdrone-pretrained")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
runs = root / args.runs_dir
cards = []
for summary_file in sorted(runs.glob("50m*/summary.json")):
    folder = summary_file.parent
    data = json.loads(summary_file.read_text())
    web_video = folder / "demo.mp4"
    if not web_video.exists():
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(folder / "annotated.mp4"),
                        "-c:v", "libx264", "-threads", "4", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(web_video)], check=True)
    prefix = folder.relative_to(root / "outputs").as_posix()
    counts = "".join(f"<tr><td>{escape(row['vehicle_class'])}</td><td>{escape(row['direction'])}</td><td>{row['count']}</td></tr>" for row in data["counts"])
    validation = data["validation"]["status"]
    cards.append(f"""<section><h2>{escape(data['camera_id'])}</h2>
      <video controls preload="metadata" src="{prefix}/demo.mp4" poster="{prefix}/latest-preview.jpg"></video>
      <p><b>{data['total_crossings']} lượt qua vạch do model đếm</b> · {data['observation']['duration_seconds']:.2f} giây ·
      {data['runtime']['processed_frames_per_second']:.1f} frame/s khi xử lý · Kiểm chứng: {escape(validation)}</p>
      <table><thead><tr><th>Loại xe</th><th>Hướng theo camera</th><th>Lượt</th></tr></thead><tbody>{counts}</tbody></table>
      <p><a href="{prefix}/events.csv">CSV sự kiện</a> · <a href="{prefix}/counts.csv">CSV theo thời gian</a> ·
      <a href="{prefix}/summary.json">Thông số và giới hạn</a> · <a href="{prefix}/demo.mp4" download>Tải video demo</a></p></section>""")
page = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Traffic counting — server 152</title><style>
body{font:16px system-ui;background:#f4f6fa;color:#182332;max-width:1100px;margin:32px auto;padding:0 20px}
h1{font-size:30px}section{background:white;border:1px solid #dae1eb;border-radius:12px;margin:24px 0;padding:24px}
video{width:100%;border-radius:8px}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #e6eaf0}
a{color:#1755b7}.note{background:#fff4d5;padding:18px;border-radius:8px;line-height:1.6}p{line-height:1.6}
</style><h1>Đếm xe qua vạch — thử nghiệm trên server 152</h1>
<p>Video → phát hiện xe → tracking → đếm theo hướng/loại → CSV. Checkpoint YOLOv8m–VisDrone tải sẵn; không train thêm tại server.</p>
<div class="note">Đây là kết quả thử nghiệm trên video UIT-ADrone lịch sử, chưa phải lưu lượng hiện tại tại dự án.
Video ngắn không đại diện cả giờ; chưa tự đưa counts vào SUMO khi chưa kiểm chứng và gắn road/edge.
Precision/recall của bbox không phải độ chính xác counting.</div>
<p>Nguồn: <a href="https://uit-together.github.io/datasets/UIT-ADrone/">UIT-ADrone</a> ·
<a href="dataset-index-audit.json">Audit nhãn</a> · <a href="visdrone-pretrained/detection-check.json">Kiểm tra bbox</a> ·
<a href="environment.json">Môi trường GPU</a></p>""" + "".join(cards) + "</html>"
(root / "outputs/index.html").write_text(page, encoding="utf-8")
print("Built", root / "outputs/index.html", "with", len(cards), "samples")
