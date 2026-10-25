# 1. 제출 흐름

과제는 원본 저장소를 직접 수정하지 않고 아래 순서로 제출합니다.

```text
원본 저장소 Fork
→ 내 저장소 Clone
→ 과제 Branch 생성
→ 과제 작성
→ Commit과 Push
→ 원본 저장소로 Pull Request
```

원본 저장소: [https://github.com/bjc1102/ai-agent-repo2](https://github.com/bjc1102/ai-agent-repo2)

# 2. 원본 저장소 Fork

원본 저장소 오른쪽 위의 `Fork`를 선택합니다.

Owner는 본인의 GitHub 계정을 선택합니다.\
Repository name은 그대로 두고 `Copy the main branch only`를 선택한 상태에서 `Create fork`를 누릅니다.

Fork는 처음 한 번만 진행합니다.\
이후 과제는 같은 Fork 저장소에 Branch를 새로 만들어 제출합니다.

# 3. Fork 저장소 Clone

아래 `{github-id}`를 본인의 GitHub ID로 바꿉니다.

```bash
git clone https://github.com/{github-id}/ai-agent-repo2.git
cd ai-agent-repo2
git remote add upstream https://github.com/bjc1102/ai-agent-repo2.git
```

`origin`은 본인의 Fork, `upstream`은 수업 원본 저장소입니다.

# 4. 원본 저장소와 동기화

과제를 시작하기 전에 Fork의 `main`을 최신 상태로 맞춥니다.

```bash
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main
```

# 5. 과제 Branch 생성

주차와 GitHub ID를 포함한 Branch를 만듭니다.

```bash
git switch -c week-01/{github-id}
```

과제 파일은 안내된 경로에 작성합니다.

```text
week-01/{github-id}/
```

# 6. Commit과 Push

변경 파일을 확인한 뒤 본인의 과제 파일만 Commit합니다.

```bash
git status
git add week-01/{github-id}
git commit -m "submit: week-01 {github-id}"
git push -u origin week-01/{github-id}
```

# 7. Pull Request 생성

원본 저장소의 `Pull requests`에서 `New pull request`를 선택합니다.\
Fork가 보이지 않으면 `compare across forks`를 누릅니다.

다음 기준으로 설정합니다.

| 항목 | 선택 값 |
|---|---|
| base repository | `bjc1102/ai-agent-repo2` |
| base | `main` |
| head repository | `{github-id}/ai-agent-repo2` |
| compare | `week-01/{github-id}` |

변경된 파일이 본인의 과제 폴더뿐인지 확인한 뒤 `Create pull request`를 누릅니다.

PR 제목은 아래 형식을 사용합니다.

```text
[1주차] {이름} 과제 제출
```

# 8. 제출 전 확인

- API Key, `.env`, 개인정보를 올리지 않았는가
- Branch와 과제 경로가 맞는가
- 다른 수강생의 파일을 수정하지 않았는가
- `Files changed`에 내 과제 파일만 보이는가
- PR의 base가 원본 저장소 `main`인가

# 9. AI 도구로 제출할 때

Claude Code나 Codex 같은 도구로 Fork 확인, 동기화, Branch 생성, Commit, Push, PR 작성까지 할 수 있습니다.\
다만 Push와 PR은 GitHub에 변경을 남기므로 실행 전에 변경 파일과 인증 정보 포함 여부를 직접 확인해야 합니다.

요청할 때는 다음 정보를 함께 전달해 주세요.

```text
원본 저장소 URL
GitHub ID
과제 주차와 제출 경로
Branch 이름
PR 제목
```

# 10. 참고 자료

- [https://docs.github.com/en/pull-requests/how-tos/work-with-forks/fork-a-repo](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/fork-a-repo)
- [https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request-from-a-fork](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request-from-a-fork)
