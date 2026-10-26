# 내 컴퓨터(데스크탑)로 파일럿 서버 운영하기

파일럿 기간(11/9~11/29) 동안 내 컴퓨터를 서버로 쓰는 방법이다. 실행 도우미(`python -m etfrec desktop`)가 다음을 한 번에 처리한다.
- 첫 실행 준비: 번들 학습, 운영 등록부, 관리자 계정
- 서버와 Cloudflare 터널을 함께 띄우기
- 서버나 터널이 멈추면 다시 켜기(응답이 3번 연속 없을 때도)
- 켜져 있는 동안 절전 막기
- 시작할 때와 매일 새벽 4시에 백업(최근 14개 보관)

24시간 켜 둘 자신이 없으면 Render 배포(저장소 README)가 더 안정적이다.

## 1. 준비물 (이번 주에 한 번)

| 항목 | 윈도우 | 맥 |
| --- | --- | --- |
| Python 3.11 이상(3.12 권장) | python.org 설치 파일(설치할 때 "Add python.exe to PATH" 체크) 또는 `winget install Python.Python.3.12` | `brew install python@3.12` 또는 python.org 설치 파일 |
| cloudflared(외부 공개용) | `winget install --id Cloudflare.cloudflared` | `brew install cloudflared` |
| 저장소 | `git clone https://github.com/kyounghob/forclaudekyoungho.git` 뒤 `git checkout claude/pensive-goldberg-dzposy` (또는 GitHub에서 이 브랜치를 ZIP으로 내려받기) | 같음 |

컴퓨터는 메모리 4GB 이상을 권장한다. 메모리가 넉넉하면 첫 실행 때 보고서와 같은 15,000명 규모 번들을 학습한다(약 1분).

윈도우에서 미리 알아 둘 것:
- **설치 위치**: 저장소는 `C:\etf`처럼 짧은 경로에 둔다. 경로가 길면 패키지 설치 때 윈도우의 경로 길이 제한(260자)에 걸릴 수 있다.
- **폴더 이동 금지**: 첫 실행 뒤에는 폴더를 옮기지 않는다. 운영 기록이 번들 위치를 절대 경로로 기억한다.
- **PATH 반영**: winget으로 cloudflared를 설치한 직후에는 명령 창을 새로 열어야 PATH가 반영된다. 실행 도우미는 기본 설치 위치(`C:\Program Files (x86)\cloudflared\`)도 찾아본다. 다른 곳에 설치했다면 실행 파일 뒤에 `--cloudflared "경로\cloudflared.exe"`를 붙인다.
- **ZIP으로 받았을 때**: `start-windows.bat`을 처음 열 때 "Windows의 PC 보호" 창이 뜨면 "추가 정보 → 실행"을 누른다. git clone으로 받으면 뜨지 않는다.
- **한글 인코딩**: 실행 파일이 Python을 UTF-8 모드(`PYTHONUTF8=1`)로 띄우므로 한글 데이터·로그가 깨지지 않는다. 명령을 직접 실행할 때도 프로그램이 파일 인코딩을 모두 UTF-8로 지정해 둔다.

## 2. 처음 켜 보기

- 윈도우: 저장소 폴더의 `deploy\desktop\start-windows.bat`을 더블클릭한다.
- 맥: `deploy/desktop/start-mac.command`를 더블클릭한다. 처음 한 번은 오른쪽 클릭 → 열기를 누른다.

첫 실행에서 일어나는 일:
1. 가상환경을 만들고 패키지를 설치한다(몇 분).
2. 번들을 학습하고 운영 등록부를 만든다.
3. 관리자 아이디와 비밀번호를 묻는다.

그다음 창에 접속 주소가 나온다. 창을 닫으면 서버도 꺼지므로 파일럿 동안 열어 둔다. 끌 때는 그 창에서 Ctrl+C를 누른다.

## 3. 접속 주소 정하기

| 방식 | 언제 | 설정 |
| --- | --- | --- |
| 임시 주소(자동) | 리허설 | cloudflared만 설치돼 있으면 `https://…trycloudflare.com` 주소가 창과 `runs/desktop/address.txt`에 나온다. **다시 켤 때마다 주소가 바뀐다** |
| 고정 주소(토큰) | 파일럿 본 기간 | 아래 순서대로 토큰을 받아 `runs/desktop/tunnel_token.txt`에 붙여 넣으면 다음 실행부터 고정 주소로 연결된다 |
| 같은 와이파이 | 강의실 시연 | cloudflared가 없거나 `--tunnel none`이면 같은 망에서 `http://내 컴퓨터 IP:8000`으로만 접속된다. 윈도우 방화벽 창이 뜨면 '개인 네트워크'만 허용한다 |

고정 주소 만들기(도메인이 필요하다):
1. Cloudflare 계정을 만들고 도메인을 연결한다. Cloudflare에서 사거나, 다른 곳에서 산 도메인의 네임서버를 Cloudflare로 바꾼다.
2. Cloudflare 대시보드의 Zero Trust → Networks → Tunnels에서 터널을 만든다(커넥터: cloudflared). 메뉴 이름은 바뀔 수 있다.
3. 설치 안내에 나오는 토큰(긴 문자열)을 복사해 `runs/desktop/tunnel_token.txt`에 붙여 넣는다. 이 파일은 저장소에 올리지 않는다(`runs/`는 git 제외).
4. 같은 화면의 Public Hostname에 `learn.내도메인`을 만들고 서비스 주소를 `http://127.0.0.1:8000`으로 둔다. 윈도우에서 `localhost`는 IPv6(::1)로 먼저 연결될 수 있으므로 숫자 주소를 쓴다.
5. 실행 파일을 다시 켜고 `https://learn.내도메인`으로 접속되는지 확인한다.

토큰은 명령줄에 쓰지 않는다. 실행 도우미가 환경변수로만 cloudflared에 넘긴다.

## 4. 3주 동안 켜 두기

- **절전**: 실행 도우미가 켜져 있는 동안은 유휴 절전을 막는다. 노트북은 덮개를 닫으면 잠들 수 있으니 전원 설정에서 '덮개를 닫을 때: 아무것도 안 함'으로 바꾸고 전원을 연결해 둔다.
- **윈도우 전원**: 설정 → 시스템 → 전원(및 배터리)에서 '절전 모드로 전환'을 '안 함'으로 둔다. 화면 끄기는 괜찮다.
- **윈도우 업데이트**: 설정 → Windows 업데이트 → '업데이트 일시 중지'로 파일럿 기간(11/2~11/30) 동안 미룬다. 자동 재시작을 막기 위해서다.
- **자동 시작**: 재부팅된 뒤에도 다시 켜지게 등록한다. 처음 한 번은 직접 실행해 관리자 계정을 만든 뒤에 등록한다.
  - 윈도우: Win+R → `shell:startup` 입력 → 열린 폴더에 `start-windows.bat`의 바로 가기를 만든다. 바로 가기 속성의 대상 끝에 ` --no-prompt`를 붙인다. 로그인할 때 켜지므로 재부팅 뒤 한 번 로그인해야 한다.
  - 맥: 저장소 폴더의 터미널에서 다음을 실행한다. 로그인할 때 켜지고 꺼지면 다시 켜진다.
    ```bash
    sed "s#REPO_PATH#$(pwd)#g" deploy/desktop/com.etfrec.pilot.plist > ~/Library/LaunchAgents/com.etfrec.pilot.plist
    launchctl load ~/Library/LaunchAgents/com.etfrec.pilot.plist
    ```
- **인터넷**: 유선 연결을 권장한다. 공유기를 재시작하면 터널은 스스로 다시 연결된다.

## 5. 백업

- 자동 백업: 시작할 때와 매일 4시에 `runs/web/backups/etfrec-날짜.db`가 생기고, 최근 14개만 남는다.
- 디스크 고장에 대비해 백업 폴더를 OneDrive·iCloud 같은 동기화 폴더로 바꿀 수 있다. 실행 파일 뒤에 `--backup-dir "동기화 폴더 경로"`를 붙인다.
- 또는 주 1회 관리자 메뉴의 ‘분석 자료 내려받기(zip)’를 받아 둔다.

## 6. 매일 점검 (1분)

- 접속 주소 뒤에 `/?admin=1`을 붙여 관리자로 로그인하면 ‘파일럿 보고서 보기’에서 이용 흐름이 보인다.
- 문제가 있으면 `runs/desktop/` 폴더를 본다.
  - `desktop.log`: 재시작·백업 기록
  - `server.log`, `tunnel.log`
- 서버가 멈춘 시간(재시작 기록)은 파일럿 보고서의 해석에 함께 적는다.

## 7. 자주 생기는 문제

| 증상 | 해결 |
| --- | --- |
| 참가자에게 준 주소가 안 열린다 | 임시 주소였다면 다시 켤 때 바뀐 것이다. 본 기간에는 고정 주소(토큰)를 쓴다 |
| "포트 8000을 이미 다른 프로그램이 쓰고 있습니다" | 이전에 켠 서버가 남아 있다. 작업 관리자(맥: 활동 모니터)에서 python을 끄거나 `--port 8001`로 켠다 |
| 같은 와이파이로 접속했는데 로그인이 안 된다 | `--tunnel none`으로 켰는지 확인한다. 이 방식에서만 HTTP 로그인이 된다 |
| 실행 창에 "Python 3.11 or newer is required"가 나온다 | python.org에서 Python 3.12를 설치하면서 "Add python.exe to PATH"를 체크한 뒤 다시 실행한다 |
| 실행 창에 "Package installation failed"가 나온다 | 인터넷 연결을 확인하고 다시 실행한다. 실행 파일이 설치가 끝났는지 기억하므로 실패한 설치는 다음 실행 때 다시 한다 |
| 관리자 비밀번호를 잊었다 | 실행 창을 끄고 저장소 폴더에서 `.venv\Scripts\python -m etfrec web reset-password --username admin`(맥: `.venv/bin/python …`)을 실행한다 |
