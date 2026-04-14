from typing import Annotated, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator
from playwright.async_api import Page

from interact_mcp.config import DEFAULT_LIMIT
from interact_mcp.state import ref_locator


class Action(BaseModel):
    mutates: ClassVar[bool] = True
    wait: str | None = None


class ObservationAction(Action):
    mutates: ClassVar[bool] = False


class TargetedAction(Action):
    ref: str | None = None
    selector: str | None = None

    @model_validator(mode="after")
    def _require_target(self):
        if not self.ref and not self.selector:
            raise ValueError("Provide ref or selector")
        return self

    def _locator(self, page: Page):
        return page.locator(ref_locator(self.ref)) if self.ref else page.locator(self.selector)


class _CoordinateTargetMixin(TargetedAction):
    x: int | None = None
    y: int | None = None

    @model_validator(mode="after")
    def _require_target(self):
        if not self.ref and not self.selector and (self.x is None or self.y is None):
            raise ValueError("Provide ref, selector, or both x and y")
        return self


class ClickAction(_CoordinateTargetMixin):
    type: Literal["click"] = "click"

    async def execute(self, page: Page):
        if self.ref:
            await self._locator(page).click()
        elif self.selector:
            await page.click(self.selector)
        else:
            await page.mouse.click(self.x, self.y)


class HoverAction(_CoordinateTargetMixin):
    type: Literal["hover"] = "hover"
    mutates: ClassVar[bool] = False

    async def execute(self, page: Page):
        if self.ref:
            await self._locator(page).hover()
        elif self.selector:
            await page.hover(self.selector)
        else:
            await page.mouse.move(self.x, self.y)


class TypeTextAction(TargetedAction):
    type: Literal["type_text"] = "type_text"
    text: str
    clear_first: bool = True

    async def execute(self, page: Page):
        target = self._locator(page)
        if self.clear_first:
            await target.fill(self.text)
        else:
            await target.type(self.text)


class ScrollAction(Action):
    DELTA: ClassVar[dict[str, tuple[int, int]]] = {
        "down": (0, 300),
        "up": (0, -300),
        "right": (300, 0),
        "left": (-300, 0),
    }
    type: Literal["scroll"] = "scroll"
    direction: Literal["down", "up", "left", "right"] = "down"
    amount: int = 3

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v: int):
        if v <= 0:
            raise ValueError("amount must be > 0")
        return v

    async def execute(self, page: Page):
        dx, dy = self.DELTA[self.direction]
        for _ in range(self.amount):
            await page.mouse.wheel(dx, dy)


async def _ref_center(page: Page, ref: str) -> tuple[float, float]:
    box = await page.locator(ref_locator(ref)).bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


class DragAction(Action):
    type: Literal["drag"] = "drag"
    from_x: int | None = None
    from_y: int | None = None
    to_x: int | None = None
    to_y: int | None = None
    from_ref: str | None = None
    to_ref: str | None = None
    steps: int = 1

    @model_validator(mode="after")
    def _require_targets(self):
        has_from = self.from_ref or (self.from_x is not None and self.from_y is not None)
        has_to = self.to_ref or (self.to_x is not None and self.to_y is not None)
        if not has_from or not has_to:
            raise ValueError("Provide from_ref or from_x+from_y, and to_ref or to_x+to_y")
        return self

    async def execute(self, page: Page):
        if self.from_ref:
            fx, fy = await _ref_center(page, self.from_ref)
        else:
            fx, fy = self.from_x, self.from_y

        if self.to_ref:
            tx, ty = await _ref_center(page, self.to_ref)
        else:
            tx, ty = self.to_x, self.to_y

        await page.mouse.move(fx, fy)
        await page.mouse.down()
        await page.mouse.move(tx, ty, steps=self.steps)
        await page.mouse.up()


class NavigateAction(Action):
    type: Literal["navigate"] = "navigate"
    url: str

    async def execute(self, page: Page):
        await page.goto(self.url)


class EvaluateJsAction(Action):
    type: Literal["evaluate_js"] = "evaluate_js"
    script: str

    async def execute(self, page: Page):
        return await page.evaluate(self.script)


class ScreenshotAction(ObservationAction):
    type: Literal["screenshot"] = "screenshot"
    scope: str | None = None
    query: str | None = None


class WaitForAction(ObservationAction):
    type: Literal["wait_for"] = "wait_for"
    selector: str
    state: Literal["visible", "hidden", "attached", "detached"] = "visible"
    timeout: int = 10000

    @field_validator("timeout")
    @classmethod
    def _positive_timeout(cls, v: int):
        if v <= 0:
            raise ValueError("timeout must be > 0")
        return v

    async def execute(self, page: Page):
        await page.wait_for_selector(
            self.selector, state=self.state, timeout=self.timeout
        )
        return f"'{self.selector}' is {self.state}"


class UploadFileAction(TargetedAction):
    type: Literal["upload_file"] = "upload_file"
    path: str

    async def execute(self, page: Page):
        target = self._locator(page)
        await target.set_input_files(self.path)


class KeyPressAction(Action):
    type: Literal["key_press"] = "key_press"
    key: str

    async def execute(self, page: Page):
        await page.keyboard.press(self.key)


class AnnotateAction(ObservationAction):
    type: Literal["annotate"] = "annotate"
    scope: str | None = None
    query: str | None = None
    limit: int = DEFAULT_LIMIT


class ClickElementAction(Action):
    type: Literal["click_element"] = "click_element"
    element: int

    async def execute(self, page: Page):
        raise NotImplementedError("server resolves click_element using stored element map")


class NewTabAction(ObservationAction):
    type: Literal["new_tab"] = "new_tab"
    url: str | None = None


class SwitchTabAction(ObservationAction):
    type: Literal["switch_tab"] = "switch_tab"
    index: int = 0


class CloseTabAction(ObservationAction):
    type: Literal["close_tab"] = "close_tab"
    index: int | None = None


class HttpRequestAction(ObservationAction):
    type: Literal["http_request"] = "http_request"
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None

    async def execute(self, page: Page):
        async with httpx.AsyncClient() as client:
            response = await client.request(
                self.method,
                self.url,
                headers=self.headers,
                content=self.body,
                timeout=30.0,
            )
            return f"{response.status_code} {response.reason_phrase}\n{response.text[:2000]}"


AnyAction = Annotated[
    ClickAction
    | HoverAction
    | TypeTextAction
    | ScrollAction
    | DragAction
    | NavigateAction
    | EvaluateJsAction
    | KeyPressAction
    | ScreenshotAction
    | WaitForAction
    | UploadFileAction
    | NewTabAction
    | SwitchTabAction
    | CloseTabAction
    | HttpRequestAction
    | AnnotateAction
    | ClickElementAction,
    Field(discriminator="type"),
]
