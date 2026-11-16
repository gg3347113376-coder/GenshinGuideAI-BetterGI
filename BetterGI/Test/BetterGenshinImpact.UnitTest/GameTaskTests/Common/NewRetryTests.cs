using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using BetterGenshinImpact.GameTask.Common;

namespace BetterGenshinImpact.UnitTest.GameTaskTests.Common;

public class NewRetryTests
{
    [Fact]
    public void Do_AlreadyCancelled_DoesNotRunAction()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var attempts = 0;

        Assert.ThrowsAny<OperationCanceledException>(() => NewRetry.Do(
            () => { attempts++; }, TimeSpan.Zero, ct: cancellation.Token));

        Assert.Equal(0, attempts);
    }

    [Fact]
    public void Do_AlreadyCancelled_DoesNotRunFunction()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        Assert.ThrowsAny<OperationCanceledException>(() => NewRetry.Do(
            () => 42, TimeSpan.Zero, ct: cancellation.Token));
    }

    [Fact]
    public async Task Do_CancelledDuringRetryWait_DoesNotRunAgain()
    {
        using var cancellation = new CancellationTokenSource();
        using var firstAttempt = new ManualResetEventSlim();
        var attempts = 0;
        Thread? retryWorker = null;
        var retry = Task.Run(() => NewRetry.Do(() =>
        {
            Interlocked.Increment(ref attempts);
            retryWorker = Thread.CurrentThread;
            firstAttempt.Set();
            throw new RetryException("等待游戏窗口");
        }, TimeSpan.FromSeconds(30), ct: cancellation.Token));

        Assert.True(firstAttempt.Wait(TimeSpan.FromSeconds(5)));
        Assert.True(SpinWait.SpinUntil(
            () => retryWorker?.ThreadState.HasFlag(ThreadState.WaitSleepJoin) == true,
            TimeSpan.FromSeconds(5)));
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => retry.WaitAsync(TimeSpan.FromSeconds(3)));
        Assert.Equal(1, attempts);
    }

    [Fact]
    public void Do_CancelledByAction_DoesNotRetry()
    {
        using var cancellation = new CancellationTokenSource();
        var attempts = 0;

        Assert.ThrowsAny<OperationCanceledException>(() => NewRetry.Do(() =>
        {
            attempts++;
            cancellation.Cancel();
            throw new RetryException("已停止任务");
        }, TimeSpan.Zero, ct: cancellation.Token));

        Assert.Equal(1, attempts);
    }

    [Fact]
    public void Do_DefaultToken_RetriesAndReturnsResult()
    {
        var attempts = 0;
        var result = NewRetry.Do(() =>
        {
            if (++attempts < 3)
            {
                throw new RetryException("重试");
            }
            return 42;
        }, TimeSpan.Zero);

        Assert.Equal(42, result);
        Assert.Equal(3, attempts);
    }

    [Fact]
    public void Do_ExhaustedRetries_ThrowsLastFailure()
    {
        var first = new RetryException("第一次失败");
        var last = new RetryException("最后一次失败");
        var attempts = 0;

        var actual = Assert.Throws<RetryException>(() => NewRetry.Do(() =>
        {
            throw ++attempts == 1 ? first : last;
        }, TimeSpan.Zero, 2));

        Assert.Same(last, actual);
        Assert.Equal(2, attempts);
    }

    [Fact]
    public void Do_NonRetryableFailure_IsNotRetried()
    {
        var failure = new InvalidOperationException("不可重试");
        var attempts = 0;

        var actual = Assert.Throws<InvalidOperationException>(() => NewRetry.Do(() =>
        {
            attempts++;
            throw failure;
        }, TimeSpan.Zero));

        Assert.Same(failure, actual);
        Assert.Equal(1, attempts);
    }
}
