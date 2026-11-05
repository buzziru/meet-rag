// 하루 1회 Space 주소를 불러 절전을 막는다(S39b, Space의 sleep_time 48시간). 질의를 보내지 않고
// GPU와 생성 API를 쓰지 않는다. 토큰이 없어 Space가 비공개인 동안에는 404를 받는다.
const SPACE_URL = "https://ingyoun-meet-rag.hf.space/config";

export default async function handler(request, response) {
  const space = await fetch(SPACE_URL, { signal: AbortSignal.timeout(20000) });
  console.log(`keep-warm: Space 응답 ${space.status}`);
  response.status(200).json({ space: space.status });
}
