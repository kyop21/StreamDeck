from typing import List, Dict, Any
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant
from PyQt5.QtGui import QColor, QFont


class LogTableModel(QAbstractTableModel):
    """
    스트림덱 명령 실행 기록을 실시간으로 렌더링하는 커스텀 QAbstractTableModel.
    8부 Model/View 아키텍처 및 조건부 서식(ForegroundRole) 적용.
    """
    HEADERS = ["시각", "버튼 ID", "버튼 제목", "액션 타입", "실행 상태"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logs: List[Dict[str, Any]] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.logs)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.logs):
            return QVariant()

        row_data = self.logs[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return str(row_data.get("time", ""))
            elif col == 1:
                return f"#{row_data.get('button_id', '')}"
            elif col == 2:
                return str(row_data.get("title", ""))
            elif col == 3:
                return str(row_data.get("action_type", "")).upper()
            elif col == 4:
                return str(row_data.get("status", ""))

        elif role == Qt.TextAlignmentRole:
            if col in (0, 1, 3):
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        elif role == Qt.ForegroundRole:
            status = str(row_data.get("status", ""))
            if "SUCCESS" in status:
                return QColor("#008000")  # 클래식 Windows 녹색
            elif "FAIL" in status:
                return QColor("#800000")  # 클래식 Windows 적색
            return QColor("#000000")

        elif role == Qt.FontRole:
            if col == 1 or col == 4:
                font = QFont()
                font.setBold(True)
                return font

        return QVariant()

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section < len(self.HEADERS):
                return self.HEADERS[section]
        return QVariant()

    def add_log(self, time_str: str, button_id: int, title: str, action_type: str, status: str):
        self.beginInsertRows(QModelIndex(), 0, 0)
        self.logs.insert(0, {
            "time": time_str,
            "button_id": button_id,
            "title": title,
            "action_type": action_type,
            "status": status
        })
        # 최대 100건 유지
        if len(self.logs) > 100:
            self.logs.pop()
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self.logs.clear()
        self.endResetModel()
