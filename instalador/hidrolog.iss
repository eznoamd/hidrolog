; Instalador do Hidrolog para Windows (Inno Setup 6).
;
; Empacota a pasta gerada pelo PyInstaller (dist\Hidrolog) e, ao instalar:
;   - cria o usuário master (página "Usuário master"), se ainda não há banco;
;   - grava a identidade do laboratório (páginas opcionais), se ainda não há marca;
;   - cria o atalho no menu Iniciar (e, se pedido, na Área de Trabalho).
; Instala só para o usuário atual, sem pedir administrador, porque o banco fica na
; pasta de dados dele (%LOCALAPPDATA%\Hidrolog). Desinstalar não apaga os dados.
;
;   iscc /DVersao=0.1.0 /DOrigem=..\dist\Hidrolog hidrolog.iss

#ifndef Versao
  #define Versao "0.1.0"
#endif
#ifndef Origem
  #define Origem "dist\Hidrolog"
#endif

[Setup]
AppId={{8F3C2B1E-6A4D-4E8B-9C2F-1D7A5E3B4C60}
AppName=Hidrolog
AppVersion={#Versao}
AppVerName=Hidrolog {#Versao}
AppPublisher=Hidrolog
DefaultDirName={localappdata}\Programs\Hidrolog
DefaultGroupName=Hidrolog
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Hidrolog-Setup-{#Versao}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Hidrolog.exe
UninstallDisplayName=Hidrolog
; não consulta o Gerenciador de Reinicialização: o app vai para uma pasta do usuário
; e, em máquinas sem sessão (CI), essa consulta pode ficar esperando
CloseApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar um atalho na Área de Trabalho"; Flags: unchecked

[Files]
Source: "{#Origem}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Hidrolog"; Filename: "{app}\Hidrolog.exe"
Name: "{autodesktop}\Hidrolog"; Filename: "{app}\Hidrolog.exe"; Tasks: atalho

[Run]
Filename: "{app}\Hidrolog.exe"; Description: "Abrir o Hidrolog"; Flags: nowait postinstall skipifsilent

[Code]
const
  SENHA_MINIMA = 8;

var
  PaginaMaster: TInputQueryWizardPage;
  PaginaMarca: TInputQueryWizardPage;
  PaginaLogos: TInputFileWizardPage;

function PastaDados: String;
begin
  Result := ExpandConstant('{localappdata}\Hidrolog');
end;

{ já há um banco: é uma atualização, o master já existe }
function BancoExiste: Boolean;
begin
  Result := FileExists(PastaDados + '\hidrolog.db');
end;

{ já há uma marca: não sobrescreve a identidade do laboratório }
function MarcaExiste: Boolean;
begin
  Result := FileExists(PastaDados + '\marca\marca.toml');
end;

procedure InitializeWizard;
begin
  PaginaMaster := CreateInputQueryPage(wpSelectTasks,
    'Usuário master',
    'O master administra os usuários e os plugins do Hidrolog.',
    'Escolha o login, o nome e a senha do master. Guarde a senha: ela é pedida para '
    + 'instalar plugins e só pode ser redefinida pelo comando de administração.');
  PaginaMaster.Add('Login (sem espaços):', False);
  PaginaMaster.Add('Nome:', False);
  PaginaMaster.Add('Senha (mínimo de 8 caracteres):', True);
  PaginaMaster.Add('Confirme a senha:', True);
  PaginaMaster.Values[0] := 'admin';

  PaginaMarca := CreateInputQueryPage(PaginaMaster.ID,
    'Identidade do laboratório (opcional)',
    'O nome do laboratório e da instituição aparecem no login, na barra lateral e nas exportações.',
    'Deixe em branco para usar o Hidrolog sem identidade; dá para configurar depois na pasta '
    + 'de marca (%LOCALAPPDATA%\Hidrolog\marca).');
  PaginaMarca.Add('Sigla do laboratório:', False);
  PaginaMarca.Add('Nome do laboratório:', False);
  PaginaMarca.Add('Sigla da instituição:', False);
  PaginaMarca.Add('Nome da instituição:', False);

  PaginaLogos := CreateInputFilePage(PaginaMarca.ID,
    'Logos (opcional)',
    'Imagens em PNG ou SVG. Sem elas, o app mostra o texto LOGO no lugar.',
    'Escolha os arquivos das logos:');
  PaginaLogos.Add('Logo do laboratório:', 'Imagens (*.png;*.svg)|*.png;*.svg', '.png');
  PaginaLogos.Add('Logo da instituição:', 'Imagens (*.png;*.svg)|*.png;*.svg', '.png');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = PaginaMaster.ID then
    Result := BancoExiste
  else if (PageID = PaginaMarca.ID) or (PageID = PaginaLogos.ID) then
    Result := MarcaExiste;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Login: String;
begin
  Result := True;
  { a instalação silenciosa também "avança" pelas páginas, sem ninguém digitar:
    não valida (o master fica para a tela inicial do app, ver CriarMaster) }
  if WizardSilent then
    exit;
  if CurPageID = PaginaMaster.ID then
  begin
    Login := Trim(PaginaMaster.Values[0]);
    if (Login = '') or (Pos(' ', Login) > 0) then
    begin
      SuppressibleMsgBox('Informe um login sem espaços.', mbError, MB_OK, IDOK);
      Result := False;
    end
    else if Length(PaginaMaster.Values[2]) < SENHA_MINIMA then
    begin
      SuppressibleMsgBox('A senha precisa de pelo menos 8 caracteres.', mbError, MB_OK, IDOK);
      Result := False;
    end
    else if PaginaMaster.Values[2] <> PaginaMaster.Values[3] then
    begin
      SuppressibleMsgBox('As senhas não conferem.', mbError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;

{ texto entre aspas para o marca.toml }
function Toml(Texto: String): String;
begin
  StringChangeEx(Texto, '\', '\\', True);
  StringChangeEx(Texto, '"', '\"', True);
  Result := '"' + Trim(Texto) + '"';
end;

procedure CriarMaster;
var
  Arquivo, Nome, Parametros: String;
  Codigo: Integer;
begin
  { instalação silenciosa (/SILENT) não passa pela página: sem senha, o master
    fica para a tela inicial do app, que mostra o comando }
  if Length(PaginaMaster.Values[2]) < SENHA_MINIMA then
    exit;
  Arquivo := ExpandConstant('{tmp}\senha-master.txt');
  SaveStringsToUTF8File(Arquivo, [PaginaMaster.Values[2]], False);
  Nome := Trim(PaginaMaster.Values[1]);
  StringChangeEx(Nome, '"', '', True);
  if Nome = '' then
    Nome := Trim(PaginaMaster.Values[0]);
  Parametros := 'admin criar-master --login "' + Trim(PaginaMaster.Values[0]) + '" --nome "' + Nome
    + '" --senha-arquivo "' + Arquivo + '"';
  if not Exec(ExpandConstant('{app}\Hidrolog.exe'), Parametros, '', SW_HIDE, ewWaitUntilTerminated, Codigo)
     or (Codigo <> 0) then
    SuppressibleMsgBox('Não foi possível criar o usuário master agora. Ao abrir o Hidrolog, a tela inicial '
      + 'mostra o comando para criá-lo.', mbError, MB_OK, IDOK);
  DeleteFile(Arquivo);
end;

procedure CopiarLogo(Origem, Nome: String);
begin
  if (Origem <> '') and FileExists(Origem) then
    FileCopy(Origem, PastaDados + '\marca\' + Nome + LowerCase(ExtractFileExt(Origem)), False);
end;

procedure GravarMarca;
var
  Linhas: TArrayOfString;
  Algum: Boolean;
begin
  Algum := (Trim(PaginaMarca.Values[0]) <> '') or (Trim(PaginaMarca.Values[1]) <> '')
    or (Trim(PaginaMarca.Values[2]) <> '') or (Trim(PaginaMarca.Values[3]) <> '')
    or (PaginaLogos.Values[0] <> '') or (PaginaLogos.Values[1] <> '');
  if not Algum then
    exit;
  ForceDirectories(PastaDados + '\marca');
  SetArrayLength(Linhas, 7);
  Linhas[0] := '# Identidade do laboratório (gravada pelo instalador; pode ser editada)';
  Linhas[1] := '[laboratorio]';
  Linhas[2] := 'sigla = ' + Toml(PaginaMarca.Values[0]);
  Linhas[3] := 'nome = ' + Toml(PaginaMarca.Values[1]);
  Linhas[4] := '[instituicao]';
  Linhas[5] := 'sigla = ' + Toml(PaginaMarca.Values[2]);
  Linhas[6] := 'nome = ' + Toml(PaginaMarca.Values[3]);
  SaveStringsToUTF8File(PastaDados + '\marca\marca.toml', Linhas, False);
  CopiarLogo(PaginaLogos.Values[0], 'logo');
  CopiarLogo(PaginaLogos.Values[1], 'instituicao');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not BancoExiste then
      CriarMaster;
    if not MarcaExiste then
      GravarMarca;
  end;
end;
