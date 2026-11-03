"""Small native editor: every choice comes from this character's own inventory."""
from pathlib import Path
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTabWidget,QWidget,QFormLayout,
    QComboBox,QHBoxLayout,QPushButton,QDialogButtonBox,QSizePolicy,QFileDialog)
from .interaction_config import InteractionConfig,TRIGGERS


class InteractionDialog(QDialog):
    saved = Signal()

    def __init__(self, config:InteractionConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(f'{config.role.name} · 角色互动设置')
        self.resize(490,460)
        self.setStyleSheet('''
            QWidget { background:#f2f8fd; color:#173552; font-size:14px; }
            QComboBox { background:white; border:1px solid #b6c9da; border-radius:6px; padding:6px; }
            QPushButton { background:#e0edfa; border:1px solid #b6c9da; border-radius:6px; padding:7px 12px; }
            QComboBox:disabled,QPushButton:disabled { color:#8293a5; }
            QTabWidget::pane { border:1px solid #b6c9da; }
            QTabBar::tab { padding:9px 16px; background:#e0edfa; }
            QTabBar::tab:selected { background:white; }
        ''')
        layout = QVBoxLayout(self)
        title = QLabel(f'为 {config.role.name} 选择互动内容')
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setStyleSheet('font-size:18px; font-weight:600; padding:6px 0;')
        layout.addWidget(title)
        note = QLabel('只修改这个角色。保存后立即生效，聊天和记忆会保留。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.rows = {}
        catalog = config.catalog()
        values = config.load()
        for key,title in zip(TRIGGERS,('点击头部','点击身体','随机待机')):
            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(16,20,16,20)
            mode = QComboBox()
            for label,value in [('保留角色默认互动','default'),('自定义','custom'),('关闭这个触发','off')]:mode.addItem(label,value)
            form.addRow('互动方式',mode)
            widgets = {'mode':mode}
            for field,group,label in [('action','actions','动作'),('expression','expressions','表情'),('voice','voices','语音')]:
                combo = QComboBox()
                combo.addItem('无','')
                combo.setMinimumContentsLength(16)
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
                for identifier,item in catalog[group].items():combo.addItem(item['label'],identifier)
                index = combo.findData(values[key][field])
                combo.setCurrentIndex(max(0,index))
                widgets[field] = combo
                if field=='voice':
                    row = QHBoxLayout()
                    row.addWidget(combo,1)
                    browse = QPushButton('导入音频…')
                    browse.clicked.connect(lambda _checked=False,trigger=key:self.import_audio(trigger))
                    row.addWidget(browse)
                    form.addRow(label,row)
                    widgets['browse'] = browse
                else:form.addRow(label,combo)
            hint = QLabel('随机待机仍间隔约 45–100 秒，点击和拖动优先。' if key=='idle' else
                          '点击可同时触发所选动作、表情和语音；拖动不触发。')
            hint.setWordWrap(True)
            form.addRow(hint)
            self.rows[key] = widgets
            mode.currentIndexChanged.connect(lambda _index,trigger=key:self.update_enabled(trigger))
            mode.setCurrentIndex(max(0,mode.findData(values[key]['mode'])))
            self.update_enabled(key)
            self.tabs.addTab(page,title)
        note = QLabel('动作播放一次，最长约 12 秒后恢复。语音遵守全局静音，聊天朗读优先。\n音频支持 WAV / MP3 / OGG；导入会保留一份本机副本。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel('原设置无法读取，目前显示默认值；保存可重新设置。' if config.read_failed else '')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel|
                                      QDialogButtonBox.StandardButton.RestoreDefaults)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText('恢复默认')
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.restore_defaults)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def update_enabled(self, key):
        row = self.rows[key]
        enabled = row['mode'].currentData()=='custom'
        for field in ('action','expression','voice','browse'):row[field].setEnabled(enabled)

    def restore_defaults(self):
        for row in self.rows.values():row['mode'].setCurrentIndex(0)
        self.status.setText('点击保存后恢复角色默认互动。')

    def import_audio(self, key):
        path,_ = QFileDialog.getOpenFileName(self,'导入角色语音','','音频 (*.wav *.mp3 *.ogg)')
        if not path:return
        try:choice = self.config.import_voice(Path(path))
        except (OSError,ValueError) as error:
            self.status.setText(str(error) if isinstance(error,ValueError) else '无法复制音频，请检查文件权限。')
            return
        for row in self.rows.values():
            row['voice'].addItem(Path(path).stem+'（已导入）',choice)
        self.rows[key]['voice'].setCurrentIndex(self.rows[key]['voice'].findData(choice))
        self.status.setText('音频已导入；点击保存后应用到所选触发。')

    def save(self):
        values = {key:{field:row[field].currentData() for field in ('mode','action','expression','voice')}
                  for key,row in self.rows.items()}
        try:self.config.save(values)
        except (ValueError,OSError) as error:
            self.status.setText(str(error) if isinstance(error,ValueError) else '保存失败，请检查目录权限。')
            return
        self.saved.emit()
        self.accept()
