// WIN-01 feasibility shell. Financial values and formulas come only from Python07.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;

public class DemoRow {
    public int Number {get;set;}
    public string Label {get;set;}
    public string Origin {get;set;}
}
public class WpfSpike : Window {
    static Stopwatch clock=Stopwatch.StartNew();
    string python,root,workspace,metrics,sourceSha;
    JavaScriptSerializer json=new JavaScriptSerializer(){MaxJsonLength=2000000,RecursionLimit=50};
    List<Dictionary<string,object>> events=new List<Dictionary<string,object>>();
    Process worker; string current; bool opened=false,terminal=false,probeMode=false; int rotation=0;double zoom=1,dpi=1,maxGap=0,lastBeat=0;
    TextBlock status,source;TextBox result;Image image;DataGrid table;Button cancel;ProgressBar progress;ComboBox scales;Grid content;
    DispatcherTimer deadline=new DispatcherTimer(),heartbeat=new DispatcherTimer();
    public WpfSpike(string[] args) {
        if(args.Length!=4&&args.Length!=5)throw new ArgumentException("Trusted launcher requires python root workspace metrics");
        probeMode=args.Length==5&&args[4]=="--probe";
        python=Path.GetFullPath(args[0]);root=Path.GetFullPath(args[1]);workspace=Path.GetFullPath(args[2]);metrics=Path.GetFullPath(args[3]);
        var manifest=(Dictionary<string,object>)json.DeserializeObject(File.ReadAllText(Path.Combine(workspace,"manifest.json"),Encoding.UTF8));sourceSha=(string)manifest["sha256"];
        Title="WIN-01 · WPF · Финансовые документы";Width=1120;Height=700;FontSize=14;Background=new SolidColorBrush(Color.FromRgb(245,249,246));Foreground=new SolidColorBrush(Color.FromRgb(24,61,44));
        content=new Grid(){Margin=new Thickness(16,12,16,12)};Content=content;
        foreach(var h in new[]{GridLength.Auto,GridLength.Auto,GridLength.Auto,GridLength.Auto,new GridLength(1,GridUnitType.Star),GridLength.Auto,GridLength.Auto,new GridLength(100)})content.RowDefinitions.Add(new RowDefinition(){Height=h});
        Add(new TextBlock(){Text="Финансовые документы · проверка Windows",FontSize=20,FontWeight=FontWeights.SemiBold,Margin=new Thickness(0,0,0,8)},0);
        Add(new TextBlock(){Text="Собственный вымышленный пример · МСФО · группа · 2025 год · млн RUB",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,0,0,8)},1);
        var bar=new WrapPanel();Add(bar,2);
        Button(bar,"_Открыть PDF","openPdf",OpenPdf);Button(bar,"Учебный _пример","demoPdf",()=>SelectPdf(Path.Combine(workspace,"own-demo-v1.pdf")));Button(bar,"Рассчитать _маржу","calculate",()=>Start("calculate"));Button(bar,"_Фоновая задача","backgroundJob",()=>Start("slow"));cancel=Button(bar,"О_тменить","cancelJob",()=>Cancel("Задание отменено. Финансового ответа нет."));cancel.IsEnabled=false;Button(bar,"Сбой worker","crashWorker",()=>Start("crash"));
        var sub=new WrapPanel();Add(sub,3);Button(sub,"_Повернуть страницу","rotatePage",()=>{rotation=(rotation+90)%360;Start("render");});sub.Children.Add(new TextBlock(){Text="Масштаб страницы: ",VerticalAlignment=VerticalAlignment.Center});
        scales=new ComboBox(){Width=100,Margin=new Thickness(4),ItemsSource=new[]{"100%","125%","150%","200%"},SelectedIndex=0};AutomationProperties.SetName(scales,"Масштаб страницы");scales.SelectionChanged+=(s,e)=>{zoom=new[]{1.0,1.25,1.5,2.0}[scales.SelectedIndex];Start("render");};sub.Children.Add(scales);
        Button(sub,"Высокий _контраст","highContrast",Contrast);Button(sub,"Крупный _текст","largeText",()=>{FontSize=19;Record("large_text");});
        var split=new Grid(){Margin=new Thickness(0,8,0,8)};split.ColumnDefinitions.Add(new ColumnDefinition(){Width=new GridLength(1,GridUnitType.Star)});split.ColumnDefinitions.Add(new ColumnDefinition(){Width=new GridLength(8)});split.ColumnDefinitions.Add(new ColumnDefinition(){Width=new GridLength(1,GridUnitType.Star)});Add(split,4);
        table=new DataGrid(){AutoGenerateColumns=false,IsReadOnly=true,EnableRowVirtualization=true,EnableColumnVirtualization=true,SelectionMode=DataGridSelectionMode.Single,SelectionUnit=DataGridSelectionUnit.FullRow};
        VirtualizingPanel.SetVirtualizationMode(table,VirtualizationMode.Recycling);ScrollViewer.SetCanContentScroll(table,true);AutomationProperties.SetName(table,"Техническая таблица: 10000 строк, не финансовые факты");
        table.Columns.Add(new DataGridTextColumn(){Header="№",Binding=new Binding("Number"),SortMemberPath="Number",Width=65});table.Columns.Add(new DataGridTextColumn(){Header="Учебная строка",Binding=new Binding("Label"),Width=190});table.Columns.Add(new DataGridTextColumn(){Header="Происхождение",Binding=new Binding("Origin"),Width=300});
        var rows=new ObservableCollection<DemoRow>(Enumerable.Range(1,10000).Select(n=>new DemoRow(){Number=n,Label="Техническая строка "+n,Origin="Это нагрузка таблицы, не финансовый факт"}));table.ItemsSource=rows;
        table.SelectionChanged+=(s,e)=>{if(table.SelectedItem!=null)Record("selection","row",((DemoRow)table.SelectedItem).Number);};table.Sorting+=(s,e)=>Record("table_sort","column",e.Column.SortMemberPath);split.Children.Add(table);
        var separator=new GridSplitter(){Width=6,HorizontalAlignment=HorizontalAlignment.Center,VerticalAlignment=VerticalAlignment.Stretch};Grid.SetColumn(separator,1);split.Children.Add(separator);
        var right=new DockPanel();Grid.SetColumn(right,2);split.Children.Add(right);source=new TextBlock(){Text="Источник: сначала откройте собственный PDF",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,0,0,6)};DockPanel.SetDock(source,Dock.Top);right.Children.Add(source);
        image=new Image(){HorizontalAlignment=HorizontalAlignment.Left,VerticalAlignment=VerticalAlignment.Top,Stretch=Stretch.None};AutomationProperties.SetName(image,"Страница PDF. Текстовая альтернатива расположена ниже.");right.Children.Add(new ScrollViewer(){Content=image,HorizontalScrollBarVisibility=ScrollBarVisibility.Auto,VerticalScrollBarVisibility=ScrollBarVisibility.Auto});
        progress=new ProgressBar(){Minimum=0,Maximum=100,Height=14};AutomationProperties.SetName(progress,"Ход фоновой задачи");Add(progress,5);
        status=new TextBlock(){Text="Готово. Откройте учебный пример.",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,6,0,6)};Add(status,6);
        result=new TextBox(){IsReadOnly=true,TextWrapping=TextWrapping.Wrap,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,Text="Текст источника: Revenue 120; Operating profit 18. 2025 год; млн RUB; МСФО; группа.\nСобственные учебные данные; публикация неизвестна; historical недоступен."};AutomationProperties.SetName(result,"Результат и доступный текст источника");Add(result,7);
        PreviewKeyDown+=(s,e)=>{if(e.Key==System.Windows.Input.Key.Escape){Cancel("Задание отменено. Финансового ответа нет.");e.Handled=true;} if(e.Key==System.Windows.Input.Key.O && (System.Windows.Input.Keyboard.Modifiers & System.Windows.Input.ModifierKeys.Control)!=0){OpenPdf();e.Handled=true;}};
        heartbeat.Interval=TimeSpan.FromMilliseconds(20);heartbeat.Tick+=(s,e)=>{double now=clock.Elapsed.TotalMilliseconds;maxGap=Math.Max(maxGap,now-lastBeat);lastBeat=now;};lastBeat=clock.Elapsed.TotalMilliseconds;heartbeat.Start();
        deadline.Interval=TimeSpan.FromSeconds(10);deadline.Tick+=(s,e)=>Cancel("Превышено время ожидания. Финансового ответа нет.");
        ContentRendered+=(s,e)=>{dpi=PresentationSource.FromVisual(this).CompositionTarget.TransformToDevice.M11;Record("ready","seconds",clock.Elapsed.TotalSeconds,"dpi",dpi,"framework",Environment.Version.ToString(),"system_high_contrast",SystemParameters.HighContrast);if(probeMode)Probe();};
        Closing+=(s,e)=>{Cancel("Закрытие");Record("closed","max_heartbeat_gap_ms",maxGap);};
    }
    void Add(UIElement e,int row){Grid.SetRow(e,row);content.Children.Add(e);}
    Button Button(Panel p,string text,string id,Action action){var b=new Button(){Content=text,Margin=new Thickness(0,0,6,6),Padding=new Thickness(8,5,8,5)};AutomationProperties.SetAutomationId(b,id);AutomationProperties.SetName(b,text.Replace("_",""));b.Click+=(s,e)=>action();p.Children.Add(b);return b;}
    void Record(string name,params object[] kv){var d=new Dictionary<string,object>(){{"event",name},{"t_ms",clock.Elapsed.TotalMilliseconds}};for(int i=0;i<kv.Length;i+=2)d[(string)kv[i]]=kv[i+1];events.Add(d);File.WriteAllText(metrics,json.Serialize(events),new UTF8Encoding(false));}
    void Contrast(){Background=SystemColors.WindowBrush;Foreground=SystemColors.WindowTextBrush;table.Background=SystemColors.WindowBrush;table.Foreground=SystemColors.WindowTextBrush;result.Background=SystemColors.WindowBrush;result.Foreground=SystemColors.WindowTextBrush;Record("system_palette","actual_high_contrast",SystemParameters.HighContrast);}
    Queue<Action> steps;DispatcherTimer probeTimer;
    void Later(int ms,Action action){var t=new DispatcherTimer(){Interval=TimeSpan.FromMilliseconds(ms)};t.Tick+=(s,e)=>{t.Stop();action();};t.Start();}
    void Probe(){steps=new Queue<Action>();steps.Enqueue(()=>SelectPdf(Path.Combine(workspace,"own-demo-v1.pdf")));steps.Enqueue(()=>Start("calculate"));foreach(int value in new[]{90,180,270,0}){int r=value;steps.Enqueue(()=>{rotation=r;zoom=2;Start("render");});}steps.Enqueue(()=>{var sw=Stopwatch.StartNew();var view=CollectionViewSource.GetDefaultView(table.ItemsSource);view.SortDescriptions.Clear();view.SortDescriptions.Add(new SortDescription("Number",ListSortDirection.Descending));table.SelectedItem=view.Cast<DemoRow>().Last();table.ScrollIntoView(table.SelectedItem);Record("table_probe","seconds",sw.Elapsed.TotalSeconds,"rows",table.Items.Count,"selected",((DemoRow)table.SelectedItem).Number,"realized_rows",CountRows(table));});steps.Enqueue(()=>{Start("slow");probeTimer.Stop();Later(1000,()=>{var p=worker;var sw=Stopwatch.StartNew();Cancel("Задание отменено. Финансового ответа нет.");Record("cancel_probe","signal_ms",sw.Elapsed.TotalMilliseconds);Later(300,()=>{bool alive=false;try{alive=!p.HasExited;}catch{}Record("cancel_exit_probe","still_running",alive);probeTimer.Start();});});});steps.Enqueue(()=>Start("crash"));steps.Enqueue(()=>Start("calculate"));steps.Enqueue(()=>{probeTimer.Stop();Record("probe_complete");Close();});probeTimer=new DispatcherTimer(){Interval=TimeSpan.FromMilliseconds(80)};probeTimer.Tick+=(s,e)=>{if(worker==null&&steps.Count>0)steps.Dequeue()();};probeTimer.Start();}
    static int CountRows(DependencyObject parent){int count=parent is DataGridRow?1:0;for(int i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++)count+=CountRows(VisualTreeHelper.GetChild(parent,i));return count;}
    void OpenPdf(){var d=new OpenFileDialog(){Title="Открыть собственный учебный PDF",Filter="PDF (*.pdf)|*.pdf",InitialDirectory=workspace};if(d.ShowDialog(this)==true)SelectPdf(d.FileName);}
    void SelectPdf(string path){Cancel("Смена документа");opened=false;var info=new FileInfo(path);string sha="";if(info.Length<=1000000)using(var h=SHA256.Create())using(var f=File.OpenRead(path))sha=BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant();if(sha!=sourceSha){status.Text="Этот PDF не зарегистрирован в учебном каталоге. Импорт других документов будет отдельным этапом.";result.Clear();image.Source=null;return;}opened=true;Record("file_open","sha256",sha);Start("render");}
    void Cancel(string message){if(worker==null)return;var p=worker;worker=null;current=null;terminal=true;deadline.Stop();try{if(!p.HasExited)p.Kill();}catch(InvalidOperationException){}result.Clear();status.Text=message;cancel.IsEnabled=false;Record("cancel");}
    static string Quote(string s){if(s.Contains("\"")||s.EndsWith("\\"))throw new ArgumentException("Launcher path");return "\""+s+"\"";}
    void Start(string op){
        if(!opened){status.Text="Сначала откройте собственный учебный PDF.";return;}Cancel("Новое задание");string job=Guid.NewGuid().ToString("N");current=job;terminal=false;result.Clear();progress.Value=0;cancel.IsEnabled=true;status.Text="Выполняется: "+op;Record("job_start","job",job,"operation",op);
        var p=new Process(){StartInfo=new ProcessStartInfo(python,"-u "+Quote(Path.Combine(root,"spikes/windows_01/worker.py"))+" --workspace "+Quote(workspace)){UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=new UTF8Encoding(false,true),StandardErrorEncoding=Encoding.UTF8}};worker=p;
        try {p.Start();p.StandardInput.WriteLine(json.Serialize(new{protocol="windows01-1",job=job,operation=op,zoom=zoom,rotation=rotation,dpi=dpi}));p.StandardInput.Close();deadline.Start();}
        catch(Exception){Cancel("Не удалось запустить worker. Финансового ответа нет.");Record("job_error","job",job);return;}
        Task.Run(()=>{
            Dictionary<string,object> done=null;string failure=null;int code=-1;
            // Drain diagnostics separately, bounded and discarded; never protocol/UI data.
            var drain=Task.Run(()=>{int n=0;while(p.StandardError.Read()!=-1)if(++n>65536){try{p.Kill();}catch{}break;}});
            try{while(true){var line=new StringBuilder();int ch;while((ch=p.StandardOutput.Read())!=-1 && ch!='\n'){line.Append((char)ch);if(line.Length>2000000)throw new InvalidDataException();}if(ch==-1 && line.Length==0)break;var e=(Dictionary<string,object>)json.DeserializeObject(line.ToString());if((string)e["protocol"]!="windows01-1" || (string)e["job"]!=job)throw new InvalidDataException();string kind=(string)e["type"];if(kind=="progress"){var copy=e;Dispatcher.BeginInvoke(new Action(()=>{if(worker==p&&current==job&&!terminal){progress.Value=Convert.ToInt32(copy["percent"]);status.Text=(string)copy["text"];}}));}else if(kind=="done"||kind=="error"){if(done!=null)throw new InvalidDataException();done=e;}else throw new InvalidDataException();}p.WaitForExit();code=p.ExitCode;}catch(Exception){failure="protocol_or_worker_error";try{if(!p.HasExited)p.Kill();}catch{}}
            var final=done;int exit=code;string error=failure;Dispatcher.BeginInvoke(new Action(()=>Finish(p,job,op,exit,final,error)));
        });
    }
    void Finish(Process p,string job,string op,int code,Dictionary<string,object> e,string error){
        if(worker!=p||current!=job||terminal){p.Dispose();return;}deadline.Stop();cancel.IsEnabled=false;worker=null;terminal=true;
        if(code!=0||error!=null||e==null||(string)e["type"]!="done"){status.Text="Worker завершился с ошибкой. Финансового ответа нет.";result.Clear();Record("job_error","job",job,"exit",code);p.Dispose();return;}
        try{if(op=="render"){
            var bytes=Convert.FromBase64String((string)e["png"]);if(bytes.Length>1500000)throw new InvalidDataException();var bitmap=new BitmapImage();using(var s=new MemoryStream(bytes)){bitmap.BeginInit();bitmap.CacheOption=BitmapCacheOption.OnLoad;bitmap.StreamSource=s;bitmap.EndInit();bitmap.Freeze();}image.Source=bitmap;image.Width=Convert.ToDouble(e["width"])/dpi;image.Height=Convert.ToDouble(e["height"])/dpi;image.Stretch=Stretch.Fill;
            source.Text="Собственный PDF · страница 1 · Operating profit: 18 · "+rotation+"° · "+Math.Round(zoom*100)+"%";result.Text="Текстовая альтернатива: Revenue 120; Operating profit 18.\n2025 год; млн RUB; МСФО; группа. Зелёная рамка выделяет 18. Просмотр не является финансовой сверкой.";Record("render","rotation",rotation,"zoom",zoom,"dpi",dpi,"rect",e["rect"]);
        }else{var outcome=(Dictionary<string,object>)e["outcome"];if((string)outcome["execution_status"]!="completed"||(string)outcome["financial_status"]!="answered")throw new InvalidDataException();var r=(Dictionary<string,object>)outcome["financial_result"];result.Text="Операционная маржа: "+(string)r["display_value"]+"%\nПрежняя операция operating_margin_v1: 18 / 120 × 100.\nСобственный вымышленный пример. Источник: страница 1, 2025 год, млн RUB.";Record("calculation","display",r["display_value"]);}
        status.Text="Завершено. Источник и результат доступны текстом.";progress.Value=100;Record("job_done","job",job,"operation",op);}
        catch(Exception){result.Clear();status.Text="Неверный ответ worker. Финансового ответа нет.";Record("job_error","job",job,"exit",code);}p.Dispose();
    }
    [STAThread]public static void Main(string[] args){new Application().Run(new WpfSpike(args));}
}
