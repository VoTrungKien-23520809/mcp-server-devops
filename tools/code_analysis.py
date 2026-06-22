import os
import subprocess
from . import mcp, logger


@mcp.tool()
def read_code_context(file_path: str) -> str:
    """Read the content of a specific source code file."""
    logger.info(f"Đang đọc nội dung file: {file_path}")
    if not os.path.isfile(file_path):
        return f"Error: File '{file_path}' does not exist."
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if len(content) > 10000:
            return content[:10000] + "\n...[FILE TRUNCATED]..."
        return content
    except Exception as e:
        return f"Error reading file '{file_path}': {str(e)}"


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _safe_path(path: str) -> str | None:
    """Trả về đường dẫn tuyệt đối nếu nằm trong thư mục dự án, ngược lại None."""
    resolved = os.path.abspath(path)
    if resolved.startswith(_PROJECT_ROOT):
        return resolved
    return None


@mcp.tool()
def list_directory(directory_path: str = ".") -> str:
    """List all files and folders in a given directory within the project."""
    logger.info(f"📂 AI đang quét thư mục: {directory_path}")
    safe = _safe_path(directory_path)
    if not safe:
        return "❌ Lỗi bảo mật: Không được phép truy cập ngoài thư mục dự án."
    try:
        items = os.listdir(safe)
        return f"--- Danh sách file trong '{directory_path}' ---\n" + "\n".join(items)
    except Exception as e:
        return f"❌ Không thể đọc thư mục {directory_path}: {str(e)}"


@mcp.tool()
def read_project_file(file_path: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Đọc nội dung một file trong project, có đánh số dòng để AI biết chính xác vị trí cần sửa.
    - start_line: Dòng bắt đầu đọc (mặc định: 1 = đầu file).
    - end_line: Dòng kết thúc (mặc định: 0 = đọc đến cuối file).
    """
    logger.info(f"📖 AI đang đọc file: {file_path} (dòng {start_line}-{end_line or 'EOF'})")
    safe = _safe_path(file_path)
    if not safe:
        return "❌ Lỗi bảo mật: Không được phép đọc file ngoài thư mục dự án."
    try:
        with open(safe, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        s = max(1, start_line) - 1
        e = total_lines if end_line <= 0 else min(end_line, total_lines)
        selected = all_lines[s:e]

        numbered = "".join(f"{s + i + 1:4d} | {line}" for i, line in enumerate(selected))

        MAX_CHARS = 6000
        if len(numbered) > MAX_CHARS:
            numbered = numbered[:MAX_CHARS] + f"\n... [CẮT BỚT - file có {total_lines} dòng, hãy dùng start_line/end_line để đọc phần tiếp]"

        return (
            f"--- FILE: '{file_path}' | Tổng {total_lines} dòng | Đang xem dòng {s+1}-{s+len(selected)} ---\n"
            f"{numbered}"
        )
    except FileNotFoundError:
        return f"❌ Lỗi: Không tìm thấy file '{file_path}'"
    except Exception as e:
        return f"❌ Lỗi khi đọc file {file_path}: {str(e)}"


@mcp.tool()
def search_in_file(file_path: str, keyword: str, context_lines: int = 5) -> str:
    """
    Tìm kiếm một từ khóa/chuỗi lỗi trong một file và trả về các dòng chứa từ khóa đó
    cùng với (context_lines) dòng xung quanh để AI hiểu ngữ cảnh.
    Rất hữu ích khi biết tên hàm/class/biến lỗi từ stack trace và muốn tìm nó trong code.
    """
    logger.info(f"🔍 AI đang tìm '{keyword}' trong file: {file_path}")
    safe = _safe_path(file_path)
    if not safe:
        return "❌ Lỗi bảo mật: Không được phép đọc file ngoài thư mục dự án."
    try:
        with open(safe, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        keyword_lower = keyword.lower()
        results = []
        for idx, line in enumerate(all_lines):
            if keyword_lower in line.lower():
                lo = max(0, idx - context_lines)
                hi = min(len(all_lines), idx + context_lines + 1)
                block_lines = [
                    f"{i+1:4d}{'>>'}| {all_lines[i]}".rstrip() if i == idx
                    else f"{i+1:4d}  | {all_lines[i]}".rstrip()
                    for i in range(lo, hi)
                ]
                results.append("\n".join(block_lines))

        if not results:
            return f"🔍 Không tìm thấy '{keyword}' trong file '{file_path}'."

        header = f"🔍 Tìm thấy {len(results)} kết quả cho '{keyword}' trong '{file_path}':\n"
        body = ("\n" + "-"*40 + "\n").join(results)
        output = header + body

        MAX_CHARS = 5000
        if len(output) > MAX_CHARS:
            output = output[:MAX_CHARS] + "\n... [CẮT BỚT - còn nhiều kết quả hơn]"
        return output

    except FileNotFoundError:
        return f"❌ Lỗi: Không tìm thấy file '{file_path}'"
    except Exception as e:
        return f"❌ Lỗi khi tìm kiếm trong file {file_path}: {str(e)}"


@mcp.tool()
def get_terraform_plan(tf_directory: str) -> str:
    """Run 'terraform plan' in the specified directory and return the output."""
    logger.info(f"Đang chạy terraform plan tại thư mục {tf_directory}")
    if not os.path.isdir(tf_directory):
        return f"Error: Directory '{tf_directory}' does not exist."
    try:
        result = subprocess.run(
            ["terraform", "plan", "-no-color"],
            cwd=tf_directory,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Terraform plan failed:\n{e.stderr}"
    except FileNotFoundError:
        return "Error: Terraform is not installed or not in PATH."
    except Exception as e:
        return f"Unexpected error: {str(e)}"
