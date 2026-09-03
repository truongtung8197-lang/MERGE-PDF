"""Logic xử lý PDF — tách riêng khỏi GUI để dễ test/debug."""

import os
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter


# =========================
# Natural sort (file2 < file10)
# =========================
def natural_sort_key(name: str):
    """Split string into (text, number) chunks for human-friendly sorting."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", name)
    ]


# =========================
# Parse input
# =========================
def parse_input(input_str: str):
    """
    Phân tích chuỗi input từ ô nhập liệu.

    Trả về: (list_of_pdf_paths, error_message_or_None)
    """
    raw = (input_str or "").strip()
    if not raw:
        return [], "Input rỗng. Vui lòng chọn Folder hoặc chọn Files."

    # Trường hợp nhiều file phân cách bằng ";"
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        pdf_paths = []
        for part in parts:
            p = Path(part)
            if not p.exists():
                return [], f"Không tìm thấy: {part}"
            if p.suffix.lower() != ".pdf":
                return [], f"Không phải file PDF: {part}"
            pdf_paths.append(str(p))
        if not pdf_paths:
            return [], "Danh sách file rỗng."
        return pdf_paths, None

    # Trường hợp 1 đường dẫn
    p = Path(raw)

    # Folder tồn tại
    if p.is_dir():
        pdf_files = sorted(
            [str(f) for f in p.glob("*.pdf") if f.is_file()],
            key=lambda x: natural_sort_key(os.path.basename(x)),
        )
        if not pdf_files:
            return [], f"Không tìm thấy file PDF nào trong folder: {p}"
        return pdf_files, None

    # File đơn
    if p.is_file():
        if p.suffix.lower() != ".pdf":
            return [], f"Không phải file PDF: {raw}"
        return [str(p)], None

    return (
        [],
        f"Không nhận diện được input: {raw}. Vui lòng chọn Folder hoặc chọn Files.",
    )


# =========================
# Output path handling
# =========================
def resolve_output_path(output_dir: str, filename: str):
    """
    Trả về đường dẫn output không trùng tên file đã tồn tại.
    Nếu trùng, tự động thêm hậu tố _1, _2, ...
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    name = filename.strip()
    if not name:
        name = "merged.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    candidate = output_dir / name
    if not candidate.exists():
        return str(candidate)

    stem = candidate.stem
    counter = 1
    while True:
        new_candidate = output_dir / f"{stem}_{counter}.pdf"
        if not new_candidate.exists():
            return str(new_candidate)
        counter += 1


# =========================
# Merge PDFs
# =========================
def merge_pdfs(
    pdf_paths: list[str], output_path: str, log_callback=None
) -> tuple[bool, str]:
    """
    Ghép danh sách file PDF theo đúng thứ tự trong pdf_paths.
    log_callback(msg: str) được gọi để cập nhật UI theo từng bước (optional).
    Trả về (success: bool, message: str).
    """

    def log(msg):
        if log_callback:
            log_callback(msg)

    if not pdf_paths:
        log("Error: Không có file PDF nào để ghép.")
        return False, "Không có file PDF nào để ghép."

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()
    skipped = []
    merged_count = 0

    for idx, path in enumerate(pdf_paths, start=1):
        name = os.path.basename(path)
        try:
            log(f"[{idx}/{len(pdf_paths)}] Đang xử lý: {name}")

            reader = PdfReader(path)
            # Thử decrypt với password rỗng (nhiều file chỉ set owner password)
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    pass

            # Kiểm tra lại sau khi thử decrypt
            if reader.is_encrypted:
                log(f"  ⚠️ Bỏ qua {name}: file PDF bị mã hóa, không đọc được.")
                skipped.append(name)
                continue

            writer.append(reader)
            merged_count += 1
            log(f"  ✅ Đã thêm: {name}")

        except Exception as e:
            log(f"  ⚠️ Bỏ qua {name}: lỗi đọc file ({type(e).__name__}).")
            skipped.append(name)
            continue

    if merged_count == 0:
        log("Không ghép được file nào. Kiểm tra lại danh sách input.")
        return False, "Không ghép được file nào."

    try:
        with open(output_path, "wb") as f:
            writer.write(f)
    except PermissionError:
        log(f"Error: Không có quyền ghi vào: {output_path}")
        return False, f"Không có quyền ghi vào: {output_path}"
    except Exception as e:
        log(f"Error khi ghi file output: {e}")
        return False, f"Lỗi khi ghi file output: {e}"
    finally:
        try:
            writer.close()
        except Exception:
            pass

    summary = f"Đã ghép {merged_count}/{len(pdf_paths)} file."
    if skipped:
        summary += f"\nBỏ qua: {', '.join(skipped)}"
    summary += f"\nOutput: {output_path}"

    log(f"✅ Hoàn tất: {summary}")
    return True, summary


# =========================
# Test thủ công
# =========================
if __name__ == "__main__":
    # --- Test natural sort ---
    names = ["file10.pdf", "file2.pdf", "file1.pdf", "file02.pdf"]
    print("Natural sort test:", sorted(names, key=natural_sort_key))

    # --- Test parse_input (chạy thủ công, thay path bằng folder thật) ---
    # test_dir = r"D:\path\to\pdf\folder"
    # print(parse_input(test_dir))
    # print(parse_input("path1.pdf; path2.pdf"))
    # print(parse_input("không tồn tại.pdf"))

    # --- Test merge với file mẫu ---
    # _paths, err = parse_input(test_dir)
    # if err:
    #     print("Error:", err)
    # else:
    #     merge_pdfs(_paths, str(Path(test_dir) / "test_merged.pdf"), log_callback=print)
    print("Merger core loaded OK. Bỏ comment để test thủ công.")
