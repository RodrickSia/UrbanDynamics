from types import SimpleNamespace
from PIL import Image, ImageDraw
from src.pipelines.land_price.extract import text_rows, parse_pdf

def test_scanned_grid_preserves_wrapped_rows():
    image = Image.new("L", (600,300),255)
    draw = ImageDraw.Draw(image)
    for y in (50,80,120,200,280):
        draw.line((55,y,542,y),fill=0,width=1)
    words = [{"text":"(1)","x0":60,"top":60,"bottom":70}]
    # The first row has text near its bottom and a price near its top.
    # Price-midpoint splitting used to assign this word to the following row.
    for text,x,y in [("1",60,125),("ROAD",90,125),("WRAPPED",90,182),
                     ("FROM",180,140),("TO",260,140),("10.000",345,125),
                     ("6.000",400,125),("5.000",465,125),
                     ("2",60,205),("NEXT",90,205),("FROM",180,220),
                     ("TO",260,220),("20.000",345,230),("12.000",400,230),("10.000",465,230)]:
        words.append({"text":text,"x0":x,"top":y,"bottom":y+8})
    page = SimpleNamespace(width=600,extract_words=lambda:words,
                           to_image=lambda **kwargs:SimpleNamespace(original=image))
    rows = text_rows(page)
    assert rows[0][1] == "ROAD WRAPPED"
    assert rows[1][1] == "NEXT"
    assert rows[0][-3:] == ["10.000","6.000","5.000"]

def test_pdf_continuation_and_whole_road_are_retained(monkeypatch):
    first = [["9","ĐƯỜNG SỐ 7,","FROM","TO","","",""]]
    second = [["","PHƯỜNG AN KHÁNH","WARD","WARD","88.600","53.200","44.300"],
              ["10","OTHER","TRỌN ĐƯỜNG","","97.600","58.600","48.800"]]
    pages = [SimpleNamespace(extract_text=lambda:"BẢNG GIÁ ĐẤT PHƯỜNG AN KHÁNH",extract_tables=lambda:[first]),
             SimpleNamespace(extract_text=lambda:"continued",extract_tables=lambda:[second])]
    class Document:
        def __enter__(self): return SimpleNamespace(pages=pages)
        def __exit__(self,*args): pass
    monkeypatch.setattr("src.pipelines.land_price.extract.pdfplumber.open",lambda path:Document())
    result = parse_pdf("fixture")
    assert len(result["records"]) == 2
    assert result["records"][0]["road"] == "ĐƯỜNG SỐ 7, PHƯỜNG AN KHÁNH"
    assert result["records"][1]["segment_scope"] == "whole_road"
    assert result["records"][1]["to"] == "TRỌN ĐƯỜNG"
    assert not result["rejected"]

def test_complete_pdf_supports_all_regions_and_repeated_ward_headers(monkeypatch):
    def page(title,rows):
        return SimpleNamespace(extract_text=lambda:title,extract_tables=lambda:[rows])
    pages = [page('Phụ lục II\nBẢNG GIÁ ĐẤT PHƯỜNG AN KHÁNH',
                  [['1','ROAD','FROM','TO','100','60','50']]),
             page('Phụ lục III\nBẢNG GIÁ ĐẤT XÃ MINH THẠNH',
                  [['1','OTHER','FROM','TO','200','120','100']]),
             page('Phụ lục IV\nBẢNG GIÁ ĐẤT PHƯỜNG VŨNG TÀU',
                  [['1','THÙY VÂN','FROM','TO','300','180','150']]),
             page('Phụ lục IV\nBẢNG GIÁ ĐẤT PHƯỜNG VŨNG TÀU',
                  [['2','','NEXT','END','400','240','200']])]
    class Document:
        def __enter__(self): return SimpleNamespace(pages=pages)
        def __exit__(self,*args): pass
    monkeypatch.setattr('src.pipelines.land_price.extract.pdfplumber.open',lambda path:Document())
    result = parse_pdf('fixture')
    assert result['region_counts']=={'hcmc_previous':1,'binh_duong_previous':1,'ba_ria_vung_tau_previous':2}
    assert result['records'][-1]['road']=='THÙY VÂN'
