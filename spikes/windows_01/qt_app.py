"""WIN-01 Qt feasibility shell. Trusted launcher paths; source/model strings are data."""
import time
START=time.perf_counter()
import argparse,base64,hashlib,json,os,sys,uuid
from pathlib import Path
from PySide6.QtCore import Qt,QAbstractTableModel,QModelIndex,QSortFilterProxyModel,QProcess,QTimer,Signal
from PySide6.QtGui import QPixmap,QKeySequence,QShortcut
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QTableView,QSplitter,QScrollArea,QPlainTextEdit,QFileDialog,QProgressBar,QComboBox
from common import request,decode,PROTOCOL,MAX_RESPONSE,CurrentJob

class Rows(QAbstractTableModel):
    def __init__(self):super().__init__();self.order=list(range(10000))
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else 10000
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else 3
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        row=self.order[index.row()]
        values=[row+1,'Техническая строка '+str(row+1),'Это нагрузка таблицы, не финансовый факт']
        if role in {Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.AccessibleTextRole,Qt.ItemDataRole.UserRole}:return values[index.column()]
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole:return ['№','Учебная строка','Происхождение'][section] if orientation==Qt.Orientation.Horizontal else section+1
    def sort(self,column,order):
        self.layoutAboutToBeChanged.emit()
        self.order.sort(key=(lambda n:n) if column==0 else (lambda n:'Техническая строка '+str(n+1)) if column==1 else (lambda n:0),reverse=order==Qt.SortOrder.DescendingOrder)
        self.layoutChanged.emit()

class Window(QMainWindow):
    def __init__(self,args):
        super().__init__();self.args=args;self.metrics=[];self.guard=CurrentJob();self.proc=None;self.pending=None;self.buf=b'';self.rotation=0;self.zoom=1.;self.opened=False
        self.manifest=json.loads((Path(args.workspace)/'manifest.json').read_text(encoding='utf8'))
        self.setWindowTitle('WIN-01 · Qt · Финансовые документы')
        available=self.screen().availableGeometry();self.resize(min(1120,available.width()-40),min(700,available.height()-60))
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(16,12,16,12);layout.setSpacing(9)
        title=QLabel('Финансовые документы · проверка Windows');title.setStyleSheet('font-size:20px;font-weight:600');layout.addWidget(title)
        intro=QLabel('Собственный вымышленный пример · МСФО · группа · 2025 год · млн RUB');intro.setWordWrap(True);layout.addWidget(intro)
        bar=QGridLayout();layout.addLayout(bar)
        self.open=self.button(bar,'&Открыть PDF','openPdf',self.open_pdf)
        self.demo=self.button(bar,'Учебный &пример','demoPdf',self.open_demo)
        self.calc=self.button(bar,'Рассчитать &маржу','calculate',lambda:self.start('calculate'))
        self.slow=self.button(bar,'&Фоновая задача','backgroundJob',lambda:self.start('slow'))
        self.cancel=self.button(bar,'О&тменить','cancelJob',self.cancel_job);self.cancel.setEnabled(False)
        self.crash=self.button(bar,'Сбой worker','crashWorker',lambda:self.start('crash'))
        sub=QHBoxLayout();layout.addLayout(sub)
        self.rotate=self.button(sub,'&Повернуть страницу','rotatePage',self.rotate_page)
        sub.addWidget(QLabel('Масштаб страницы:'));self.scales=QComboBox();self.scales.setAccessibleName('Масштаб страницы');self.scales.addItems(['100%','125%','150%','200%']);self.scales.currentIndexChanged.connect(self.change_zoom);sub.addWidget(self.scales)
        self.contrast=self.button(sub,'Высокий &контраст','highContrast',self.high_contrast)
        self.large=self.button(sub,'Крупный &текст','largeText',self.large_text);sub.addStretch()
        splitter=QSplitter();layout.addWidget(splitter,1)
        self.table=QTableView();self.table.setAccessibleName('Техническая таблица: 10000 строк, не финансовые факты');self.model=Rows();self.proxy=self.model;self.table.setModel(self.model);self.table.setSortingEnabled(True);self.table.sortByColumn(0,Qt.SortOrder.AscendingOrder);self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows);self.table.setColumnWidth(0,60);self.table.setColumnWidth(1,190);self.table.setColumnWidth(2,300);self.table.selectionModel().selectionChanged.connect(lambda *x:self.record('selection',row=self.table.currentIndex().row()));splitter.addWidget(self.table)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(0,0,0,0);self.source=QLabel('Источник: сначала откройте собственный PDF');self.source.setWordWrap(True);self.source.setAccessibleName('Точный источник и страница');rl.addWidget(self.source)
        self.image=QLabel('Здесь появится страница PDF с выделенной ячейкой 18');self.image.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft);self.image.setAccessibleName('Страница PDF. Текстовая альтернатива расположена ниже.');scroll=QScrollArea();scroll.setWidget(self.image);scroll.setWidgetResizable(False);rl.addWidget(scroll,1);splitter.addWidget(right);splitter.setSizes([550,520])
        self.progress=QProgressBar();self.progress.setAccessibleName('Ход фоновой задачи');layout.addWidget(self.progress)
        self.status=QLabel('Готово. Откройте учебный пример.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.result=QPlainTextEdit();self.result.setReadOnly(True);self.result.setAccessibleName('Результат и доступный текст источника');self.result.setMaximumHeight(105);self.result.setPlainText('Текст источника: Revenue 120; Operating profit 18. 2025 год; млн RUB; МСФО; группа.\nЭто собственные учебные данные. Публикация неизвестна; historical недоступен.');layout.addWidget(self.result)
        self.set_theme(False);QShortcut(QKeySequence.StandardKey.Open,self,self.open_pdf);QShortcut(QKeySequence('Escape'),self,self.cancel_job)
        self.beat=time.perf_counter();self.max_gap=0.;self.timer=QTimer(self);self.timer.timeout.connect(self.heartbeat);self.timer.start(20)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True);self.deadline.timeout.connect(lambda:self.cancel_job('Превышено время ожидания'))
        self.source.setAccessibleName('')
        self.record('constructed',seconds=time.perf_counter()-START,qt=__import__('PySide6').__version__)
        QTimer.singleShot(0,self.ready)
    def button(self,layout,text,name,fn):
        b=QPushButton(text);b.setObjectName(name);b.setAccessibleName(text.replace('&',''));b.clicked.connect(lambda checked=False:fn())
        if isinstance(layout,QGridLayout):n=layout.count();layout.addWidget(b,n//3,n%3)
        else:layout.addWidget(b)
        return b
    def record(self,event,**kw):
        self.metrics.append(dict(event=event,t=time.perf_counter(),**kw));Path(self.args.metrics).write_text(json.dumps(self.metrics,ensure_ascii=False,indent=2),encoding='utf8')
    def ready(self):
        available=self.screen().availableGeometry()
        self.record('ready',seconds=time.perf_counter()-START,dpi=self.devicePixelRatioF(),logical_dpi=self.screen().logicalDotsPerInch(),window_size=[self.width(),self.height()],available_size=[available.width(),available.height()])
        if self.args.probe:QTimer.singleShot(200,self.probe)
    def probe(self):
        # In-process component exercise; explicitly separate from real CUA/keyboard observations.
        self.steps=[lambda:self.open_demo(),lambda:self.start('calculate')]
        for r in [90,180,270,0]:
            self.steps.append(lambda r=r:self.probe_render(r))
        self.steps += [self.probe_table,self.probe_cancel,lambda:self.start('crash'),lambda:self.start('calculate'),self.probe_finish]
        self.probe_timer=QTimer(self);self.probe_timer.timeout.connect(self.probe_next);self.probe_timer.start(80)
    def probe_next(self):
        if self.guard.state=='running':return
        if self.steps:self.steps.pop(0)()
    def probe_render(self,r):self.rotation=r;self.zoom=2;self.start('render')
    def probe_table(self):
        begin=time.perf_counter();self.table.sortByColumn(0,Qt.SortOrder.DescendingOrder);self.table.selectRow(9999);self.table.scrollToBottom()
        self.record('table_probe',seconds=time.perf_counter()-begin,rows=self.model.rowCount(),selected=self.proxy.data(self.proxy.index(9999,0)),widgets=len(self.table.findChildren(QWidget)))
    def probe_cancel(self):
        self.start('slow');self.probe_timer.stop();QTimer.singleShot(1000,self.probe_cancel_now)
    def probe_cancel_now(self):
        begin=time.perf_counter();proc=self.proc;self.cancel_job();self.record('cancel_probe',signal_ms=(time.perf_counter()-begin)*1000)
        QTimer.singleShot(300,lambda:self.probe_cancel_checked(proc))
    def probe_cancel_checked(self,proc):
        try:running=proc.state()!=QProcess.ProcessState.NotRunning
        except RuntimeError:running=False
        self.record('cancel_exit_probe',still_running=running);self.probe_timer.start(80)
    def probe_finish(self):
        self.probe_timer.stop();self.grab().save(str(Path(self.args.metrics).parent/'own-window.png'));self.record('probe_complete');self.close()
    def heartbeat(self):
        now=time.perf_counter();gap=now-self.beat;self.max_gap=max(self.max_gap,gap);self.beat=now
        if gap>.08:self.record('heartbeat_gap',ms=gap*1000,state=self.guard.state)
    def set_theme(self,contrast):
        self.setStyleSheet('QWidget{background:#000;color:#fff;font-size:14px} QPushButton,QComboBox{border:2px solid #fff;padding:6px} QPushButton:focus{border:3px solid #ffff00} QTableView,QPlainTextEdit{background:#000;color:#fff;selection-background-color:#ffff00;selection-color:#000}' if contrast else 'QWidget{background:#f5f9f6;color:#183d2c;font-size:14px} QTableView,QPlainTextEdit,QScrollArea{background:#fff;color:#182a20;border:1px solid #ccdcd2} QPushButton{background:#fff;border:1px solid #568367;border-radius:4px;padding:6px} QPushButton:focus{border:2px solid #14783d} QPushButton:disabled{color:#738077} QHeaderView::section{background:#e8f1eb;padding:5px} QProgressBar::chunk{background:#24834a}')
    def high_contrast(self):self.set_theme(True);self.record('app_high_contrast')
    def large_text(self):self.setStyleSheet(self.styleSheet()+' QWidget{font-size:19px}');self.record('large_text')
    def open_pdf(self):
        path,_=QFileDialog.getOpenFileName(self,'Открыть собственный учебный PDF',self.args.workspace,'PDF (*.pdf)')
        if path:self.select_pdf(Path(path))
    def select_pdf(self,path):
        self.cancel_job();self.opened=False
        if path.stat().st_size>1_000_000 or hashlib.sha256(path.read_bytes()).hexdigest()!=self.manifest['sha256']:
            self.status.setText('Этот PDF не зарегистрирован в учебном каталоге. Импорт других документов будет отдельным этапом.');self.result.clear();self.image.clear();return
        self.opened=True;self.record('file_open',sha256=self.manifest['sha256']);self.start('render')
    def open_demo(self):self.select_pdf(Path(self.args.workspace)/'own-demo-v1.pdf')
    def rotate_page(self):self.rotation=(self.rotation+90)%360;self.start('render')
    def change_zoom(self,i):self.zoom=[1,1.25,1.5,2][i];self.start('render')
    def start(self,op):
        if not self.opened:self.status.setText('Сначала откройте собственный учебный PDF.');return
        self.cancel_job();job=uuid.uuid4().hex;self.guard.start(job);self.pending=None;self.buf=b'';self.result.clear();self.progress.setValue(0);self.cancel.setEnabled(True)
        self.status.setText('Выполняется: '+op);self.record('job_start',job=job,operation=op)
        proc=QProcess(self);self.proc=proc;proc.setProgram(self.args.python);proc.setArguments(['-u',str(Path(self.args.root)/'spikes/windows_01/worker.py'),'--workspace',self.args.workspace]);proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        proc.readyReadStandardOutput.connect(lambda:self.read(proc,job));proc.finished.connect(lambda code,status:self.finished(proc,job,op,code,status));proc.errorOccurred.connect(lambda err:self.failed(proc,job,str(err)))
        payload=json.dumps(request(job,op,self.zoom,self.rotation,self.devicePixelRatioF())).encode('utf8')+b'\n'
        proc.started.connect(lambda:(proc.write(payload),proc.closeWriteChannel()));begin=time.perf_counter();proc.start();self.record('process_start_return',ms=(time.perf_counter()-begin)*1000);self.deadline.start(10000)
    def read(self,proc,job):
        if proc is not self.proc:return
        self.buf+=bytes(proc.readAllStandardOutput())
        if len(self.buf)>MAX_RESPONSE:self.cancel_job('Слишком большой ответ worker');return
        while b'\n' in self.buf:
            line,self.buf=self.buf.split(b'\n',1)
            try:event=decode(line)
            except (ValueError,UnicodeError):self.cancel_job('Неверный ответ worker');return
            if event.get('protocol')!=PROTOCOL or event.get('job')!=job:self.cancel_job('Ответ другого задания');return
            if event.get('type')=='progress':self.progress.setValue(event['percent']);self.status.setText(event['text'])
            elif event.get('type') in {'done','error'}:
                if self.pending is not None:self.cancel_job('Повторный итог worker');return
                self.pending=event
            else:self.cancel_job('Неизвестное событие worker');return
    def failed(self,proc,job,err):
        if proc is self.proc and self.guard.current==job:self.status.setText('Ошибка worker: '+err);self.record('worker_error',job=job)
    def finished(self,proc,job,op,code,status):
        if proc is not self.proc or self.guard.current!=job:
            import shiboken6
            if shiboken6.isValid(proc):proc.deleteLater()
            return
        self.read(proc,job);self.deadline.stop();self.cancel.setEnabled(False)
        event=self.pending
        if code!=0 or status!=QProcess.ExitStatus.NormalExit or self.buf or not event or event['type']!='done':
            self.status.setText('Worker завершился с ошибкой. Финансового ответа нет.');self.result.clear();self.guard.cancel();self.record('job_error',job=job,exit=code)
        elif self.guard.accept(event):
            if op=='render':
                pix=QPixmap();pix.loadFromData(base64.b64decode(event['png'],validate=True));pix.setDevicePixelRatio(self.devicePixelRatioF());self.image.setPixmap(pix);self.image.resize(pix.deviceIndependentSize().toSize());self.source.setText('Собственный PDF · страница 1 · Operating profit: 18 · '+str(self.rotation)+'° · '+str(round(self.zoom*100))+'%');self.result.setPlainText('Текстовая альтернатива: Revenue 120; Operating profit 18.\n2025 год; млн RUB; МСФО; группа. Зелёная рамка выделяет 18. Просмотр не является финансовой сверкой.');self.record('render',rotation=self.rotation,zoom=self.zoom,rect=event['rect'],dpi=self.devicePixelRatioF())
            else:
                r=event['outcome']['financial_result'];self.result.setPlainText('Операционная маржа: '+r['display_value']+'%\nПрежняя операция operating_margin_v1: 18 / 120 × 100.\nСобственный вымышленный пример. Источник: страница 1, 2025 год, млн RUB.');self.record('calculation',display=r['display_value'],source_sha=r['inputs'][0]['document_sha256'])
            self.status.setText('Завершено. Источник и результат доступны текстом.');self.progress.setValue(100);self.record('job_done',job=job,operation=op)
        self.proc=None;proc.deleteLater()
    def cancel_job(self,message='Задание отменено. Финансового ответа нет.'):
        if self.proc is not None:
            proc=self.proc;self.proc=None;self.guard.cancel();proc.kill();self.result.clear();self.status.setText(message);self.record('cancel');self.cancel.setEnabled(False);self.deadline.stop()
    def closeEvent(self,event):
        self.cancel_job();self.record('closed',max_heartbeat_gap_ms=self.max_gap*1000);super().closeEvent(event)

def main():
    p=argparse.ArgumentParser()
    for name in ['python','root','workspace','metrics']:p.add_argument('--'+name,required=True)
    p.add_argument('--probe',action='store_true')
    args=p.parse_args();app=QApplication(sys.argv);win=Window(args);win.show();return app.exec()
if __name__=='__main__':raise SystemExit(main())
