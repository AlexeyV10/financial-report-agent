"""Actual Qt model and process UI semantics, not Streamlit AppTest."""
from pathlib import Path
import argparse,json,sys,time,unittest
sys.path.insert(0,str(Path(__file__).parent))
from PySide6.QtCore import Qt,QProcess
from PySide6.QtWidgets import QApplication,QWidget
from qt_app import Rows,Window
ROOT=Path(__file__).resolve().parents[2]
class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.win=Window(argparse.Namespace(python=sys.executable,root=str(ROOT),workspace=str(ROOT/'tmp/demo'),metrics=str(ROOT/'tmp/qt-test-ui.json'),probe=False));self.win.show();self.app.processEvents()
    def tearDown(self):self.win.close();self.app.processEvents()
    def until(self,fn,timeout=5):
        end=time.monotonic()+timeout
        while not fn() and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertTrue(fn())
    def test_modelview_sort_numeric_select_10000_without_widgets(self):
        m=self.win.model;self.assertEqual(m.rowCount(),10000);self.win.table.sortByColumn(0,Qt.SortOrder.DescendingOrder);self.assertEqual(m.data(m.index(0,0)),10000);self.win.table.selectRow(9999);self.win.table.scrollToBottom();self.app.processEvents();self.assertEqual(m.data(self.win.table.currentIndex()),1);self.assertLess(len(self.win.table.findChildren(QWidget)),50)
    def test_worker_result_crash_and_recovery(self):
        self.win.open_demo();self.until(lambda:self.win.guard.state=='done');self.win.start('calculate');self.until(lambda:self.win.guard.state=='done');self.assertIn('15.00%',self.win.result.toPlainText());self.win.start('crash');self.until(lambda:self.win.proc is None);self.assertEqual(self.win.result.toPlainText(),'');self.assertIn('ошибкой',self.win.status.text());self.win.start('calculate');self.until(lambda:self.win.guard.state=='done');self.assertIn('15.00%',self.win.result.toPlainText())
    def test_cancel_and_replacement_ignore_late_result(self):
        self.win.open_demo();self.until(lambda:self.win.guard.state=='done');self.win.start('slow');old=self.win.proc;self.until(lambda:self.win.progress.value()>5);self.win.cancel_job();self.assertEqual(self.win.result.toPlainText(),'');self.win.start('calculate');self.until(lambda:self.win.guard.state=='done');self.assertIn('15.00%',self.win.result.toPlainText());self.win.finished(old,'cancelled-old','slow',0,QProcess.ExitStatus.NormalExit);self.assertIn('15.00%',self.win.result.toPlainText())
if __name__=='__main__':unittest.main(verbosity=2)
