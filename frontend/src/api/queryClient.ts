import { MutationCache, QueryClient } from "@tanstack/react-query";
import { toast } from "../components/common/Toast";
import { errMsg } from "./client";
import { restorePersisted, startPersisting } from "./persist";

// gcTime 24시간: 다른 화면에 갔다 와도 받은 데이터를 버리지 않고 바로 보여줌 (뒤에서 최신 데이터로 갱신)
export const queryClient = new QueryClient({
  // 버튼(저장·삭제·다시 계산 등) 요청이 실패하면 화면 아래 알림으로 사유 표시.
  // 화면 안에 이미 오류 칸이 있는 것은 meta: { inlineError: true } 로 제외
  mutationCache: new MutationCache({
    onError: (e, _v, _c, m) => { if (!m.meta?.inlineError) toast(errMsg(e)); },
  }),
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, gcTime: 24 * 60 * 60 * 1000 } },
});

restorePersisted(queryClient);
startPersisting(queryClient);
